"""Iniciar producción: lista de contratación por proveedor y tareas (O-02, O-03)."""

from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from tests.proposals.test_decisions import _decide
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import OrgWorld, build_org, logged_in


def _approved(world: OrgWorld) -> TestClient:
    """El evento del harness con el presupuesto aceptado (1 línea del catálogo, costo 1000)."""
    owner = logged_in(world.members[Role.OWNER])
    budget = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}"))
    section_id = budget["version"]["sections"][0]["id"]
    _ok(
        owner.post(
            f"/api/v1/budgets/{world.ids['budget_id']}/draft/lines",
            json={"section_id": section_id, "name": "Catering propio", "unit_cost_amount": "500"},
            headers={"If-Match": str(budget["version"]["lock_version"])},
        ),
        201,
    )
    _ok(_decide(_send(owner, world), "accept", name="Ana", email="ana@x.com"))
    return owner


def _production(client: TestClient, world: OrgWorld) -> dict[str, Any]:
    return _ok(client.get(f"/api/v1/events/{world.ids['event_id']}/production"))


def test_start_production_builds_hire_list_and_suggested_tasks() -> None:
    world = build_org("a")
    _approved(world)
    production = logged_in(world.members[Role.PRODUCTION])
    started = _ok(production.post(f"/api/v1/events/{world.ids['event_id']}/start-production"))
    assert started["started"] is True

    # El harness ya trae un renglón de ejemplo; los nuevos salen de la baseline.
    by_name = {s["supplier_name"]: s for s in started["suppliers"]}
    supplier = by_name["Proveedor ejemplo"]
    assert supplier["status"] == "TO_HIRE"
    assert supplier["budgeted_cost"] == "1000.00"
    assert [i["name"] for i in supplier["items"]] == ["Producto ejemplo"]
    own = by_name[None]  # la línea libre sin proveedor
    assert [i["name"] for i in own["items"]] == ["Catering propio"]
    assert own["budgeted_cost"] == "500.00"

    titles = [t["title"] for t in started["tasks"]]
    assert "Coordinar categoría con productos" in titles
    assert any(t.startswith("Confirmar con el cliente") for t in titles)
    event = _ok(production.get(f"/api/v1/events/{world.ids['event_id']}"))
    assert event["status"] == "IN_PRODUCTION"

    # Iniciar dos veces no duplica: ya no está aprobado.
    again = production.post(f"/api/v1/events/{world.ids['event_id']}/start-production")
    assert again.status_code == 409


def test_hire_status_transitions_and_cost_visibility() -> None:
    world = build_org("a")
    _approved(world)
    production = logged_in(world.members[Role.PRODUCTION])
    started = _ok(production.post(f"/api/v1/events/{world.ids['event_id']}/start-production"))
    row = next(
        s for s in started["suppliers"] if s["supplier_name"] == "Proveedor ejemplo" and s["items"]
    )
    url = f"/api/v1/event-suppliers/{row['id']}"

    confirmed = _ok(production.patch(url, json={"status": "CONFIRMED", "notes": "Seña paga"}))
    assert (confirmed["status"], confirmed["notes"]) == ("CONFIRMED", "Seña paga")
    assert confirmed["confirmed_at"] is not None
    back = production.patch(url, json={"status": "TO_HIRE"})
    assert (back.status_code, back.json()["code"]) == (409, "hire_transition_invalid")

    # Como en la planilla de la piloto: factura cargada (con Nº y condición) y pagado.
    invoiced = _ok(
        production.patch(
            url,
            json={
                "status": "INVOICED",
                "invoice_number": " A-0003-00001234 ",
                "payment_terms": "echeck 30 días",
            },
        )
    )
    assert (invoiced["status"], invoiced["invoice_number"]) == ("INVOICED", "A-0003-00001234")
    assert invoiced["payment_terms"] == "echeck 30 días"
    late_cancel = production.patch(url, json={"status": "CANCELLED"})
    assert late_cancel.status_code == 409  # ya facturado: no se cancela
    paid = _ok(production.patch(url, json={"status": "PAID"}))
    assert paid["status"] == "PAID"
    assert paid["paid_at"] is not None

    # Otro renglón: se cancela antes de confirmar y ya no vuelve.
    other = next(s for s in started["suppliers"] if s["supplier_name"] is None)
    other_url = f"/api/v1/event-suppliers/{other['id']}"
    assert _ok(production.patch(other_url, json={"status": "CANCELLED"}))["status"] == "CANCELLED"
    assert production.patch(other_url, json={"status": "CONFIRMED"}).status_code == 409

    # Un viewer ve la lista pero no los costos.
    viewer = logged_in(world.members[Role.VIEWER])
    seen = _production(viewer, world)
    assert all(s["budgeted_cost"] is None for s in seen["suppliers"])
    assert all(i["cost_total"] is None for s in seen["suppliers"] for i in s["items"])
    assert seen["budgeted_cost"] is None
    assert viewer.patch(url, json={"notes": "x"}).status_code == 403


def test_tasks_crud_and_assignee_must_be_member() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    base = f"/api/v1/events/{world.ids['event_id']}/tasks"
    task = _ok(
        production.post(
            base,
            json={
                "title": " Pedir planos del salón ",
                "assignee_user_id": str(world.members[Role.PRODUCTION].user_id),
                "due_date": "2027-03-01",
            },
        ),
        201,
    )
    assert (task["title"], task["status"]) == ("Pedir planos del salón", "TODO")
    assert task["assignee_name"] is not None

    stranger = build_org("b").members[Role.OWNER].user_id
    bad = production.patch(f"/api/v1/tasks/{task['id']}", json={"assignee_user_id": str(stranger)})
    assert (bad.status_code, bad.json()["code"]) == (422, "assignee_not_member")
    done = _ok(production.patch(f"/api/v1/tasks/{task['id']}", json={"status": "DONE"}))
    assert done["status"] == "DONE"
    assert production.delete(f"/api/v1/tasks/{task['id']}").status_code == 204
    assert all(t["id"] != task["id"] for t in _production(production, world)["tasks"])


def test_closed_event_is_read_only() -> None:
    world = build_org("a")
    _approved(world)
    manager = logged_in(world.members[Role.MANAGER])
    base = f"/api/v1/events/{world.ids['event_id']}"
    _ok(manager.post(f"{base}/start-production"))
    _ok(manager.post(f"{base}/complete"))
    _ok(manager.post(f"{base}/close"))
    locked = manager.post(f"{base}/tasks", json={"title": "Algo"})
    assert (locked.status_code, locked.json()["code"]) == (409, "event_locked")
