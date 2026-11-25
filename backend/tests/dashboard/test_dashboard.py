"""Dashboard (A-01) con las definiciones de PRODUCT_SPEC §8, sobre datos sembrados."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from app.modules.catalog import today_ar
from tests.production.test_production import _approved
from tests.proposals.test_decisions import _decide
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import OrgWorld, build_org, logged_in


def _dashboard(client: TestClient, month: str | None = None) -> dict[str, Any]:
    return _ok(client.get("/api/v1/dashboard", params={"month": month} if month else {}))


def _budget(client: TestClient, world: OrgWorld) -> dict[str, Any]:
    return _ok(client.get(f"/api/v1/budgets/{world.ids['budget_id']}"))


def test_sent_accepted_negotiation_margin_and_conversion() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    # El harness trae un presupuesto con su propuesta enviada (activa).
    before = _dashboard(owner)
    assert before["sent"]["count"] == 1
    assert before["in_negotiation"]["count"] == 1
    assert before["accepted"] == {"count": 0, "amount": "0.00"}
    assert before["avg_margin"] is None

    _approved(world)  # envía el otro presupuesto y el cliente lo acepta
    version = _budget(owner, world)["version"]
    data = _dashboard(owner)
    assert data["sent"]["count"] == 2
    assert data["accepted"] == {"count": 1, "amount": version["sale_net"]}
    assert data["in_negotiation"]["count"] == 1  # la aceptada ya no negocia
    # Ponderado por venta: con un solo aceptado es su margen neto.
    assert data["avg_margin"] == version["margins"]["margin_net"]
    assert data["conversion"]["won"]["count"] == 1
    assert data["conversion"]["by_count"] == "1.000000"

    # Otro mes: enviado y aceptado son del período; en negociación es una foto de hoy.
    old = _dashboard(owner, "2020-01")
    assert (old["sent"]["count"], old["accepted"]["count"]) == (0, 0)
    assert old["in_negotiation"]["count"] == 1


def test_rejection_counts_as_lost() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    _ok(_decide(_send(owner, world), "reject", name="Ana", email="ana@x.com", reason="Caro"))
    data = _dashboard(owner)
    assert (data["conversion"]["won"]["count"], data["conversion"]["lost"]["count"]) == (0, 1)
    assert data["conversion"]["by_count"] == "0.000000"


def test_upcoming_events_and_margin_visibility() -> None:
    world = build_org("a")
    _approved(world)
    owner = logged_in(world.members[Role.OWNER])
    soon = (today_ar() + timedelta(days=3)).isoformat()
    _ok(owner.patch(f"/api/v1/events/{world.ids['event_id']}", json={"start_date": soon}))
    [upcoming] = _dashboard(owner)["upcoming"]
    assert (upcoming["start_date"], upcoming["status"]) == (soon, "APPROVED")
    assert Decimal(upcoming["margin"]) > 0

    viewer = logged_in(world.members[Role.VIEWER])  # ve el tablero, no los márgenes
    data = _dashboard(viewer)
    assert data["avg_margin"] is None
    assert data["upcoming"][0]["margin"] is None


def test_quoter_sees_only_their_own_budgets_and_permissions() -> None:
    world = build_org("a")
    quoter = logged_in(world.members[Role.QUOTER])
    data = _dashboard(quoter)
    assert data["own_only"] is True
    assert data["sent"]["count"] == 0  # los del harness los creó el OWNER

    production = logged_in(world.members[Role.PRODUCTION])
    assert production.get("/api/v1/dashboard").status_code == 403
    owner = logged_in(world.members[Role.OWNER])
    bad = owner.get("/api/v1/dashboard", params={"month": "2026-13"})
    assert (bad.status_code, bad.json()["code"]) == (422, "invalid_month")
    assert owner.get("/api/v1/dashboard", params={"month": "octubre"}).status_code == 422


def _ops(client: TestClient) -> list[dict[str, Any]]:
    return list(_dashboard(client)["todo"]["operations"])


def test_todo_lists_overdue_tasks_suppliers_to_confirm_and_invoices_to_pay() -> None:
    world = build_org("a")
    owner = _approved(world)
    event_id = world.ids["event_id"]
    soon = (today_ar() + timedelta(days=3)).isoformat()
    _ok(owner.patch(f"/api/v1/events/{event_id}", json={"start_date": soon}))
    started = _ok(owner.post(f"/api/v1/events/{event_id}/start-production"))
    yesterday = (today_ar() - timedelta(days=1)).isoformat()
    for title, due in (
        ("Atrasada 1", yesterday),
        ("Atrasada 2", yesterday),
        ("Hoy", today_ar().isoformat()),
    ):
        _ok(
            owner.post(f"/api/v1/events/{event_id}/tasks", json={"title": title, "due_date": due}),
            201,
        )
    _ok(owner.post(f"/api/v1/events/{event_id}/tasks", json={"title": "Sin fecha"}), 201)

    ops = {o["kind"]: o for o in _ops(owner)}
    assert ops["TASKS_OVERDUE"]["count"] == 2
    assert ops["TASKS_OVERDUE"]["date"] == yesterday
    assert ops["TASKS_TODAY"]["count"] == 1
    # Solo los proveedores reales: lo propio (sin proveedor) no se confirma.
    real = [s for s in started["suppliers"] if s["supplier_id"]]
    assert len(real) == 2
    assert len(started["suppliers"]) == 3
    assert (ops["TO_CONFIRM"]["count"], ops["TO_CONFIRM"]["date"]) == (2, soon)
    assert ops["TO_CONFIRM"]["event_id"] == str(event_id)
    assert "TO_PAY" not in ops
    assert [o["kind"] for o in _ops(owner)] == ["TASKS_OVERDUE", "TASKS_TODAY", "TO_CONFIRM"]

    invoiced, other = real
    _ok(
        owner.patch(
            f"/api/v1/event-suppliers/{invoiced['id']}",
            json={"status": "INVOICED", "invoice_number": "A-1"},
        )
    )
    ops = {o["kind"]: o for o in _ops(owner)}
    assert (ops["TO_CONFIRM"]["count"], ops["TO_PAY"]["count"]) == (1, 1)

    _ok(owner.patch(f"/api/v1/event-suppliers/{invoiced['id']}", json={"status": "PAID"}))
    _ok(owner.patch(f"/api/v1/event-suppliers/{other['id']}", json={"status": "CONFIRMED"}))
    for task in _ok(owner.get(f"/api/v1/events/{event_id}/production"))["tasks"]:
        _ok(owner.patch(f"/api/v1/tasks/{task['id']}", json={"status": "DONE"}))
    assert _ops(owner) == []


def test_todo_operations_need_production_permission_and_ignore_far_events() -> None:
    world = build_org("a")
    owner = _approved(world)
    far = (today_ar() + timedelta(days=30)).isoformat()
    _ok(owner.patch(f"/api/v1/events/{world.ids['event_id']}", json={"start_date": far}))
    _ok(owner.post(f"/api/v1/events/{world.ids['event_id']}/start-production"))
    assert _ops(owner) == []  # falta un mes: todavía no hace falta confirmar

    soon = (today_ar() + timedelta(days=2)).isoformat()
    _ok(owner.patch(f"/api/v1/events/{world.ids['event_id']}", json={"start_date": soon}))
    assert [o["kind"] for o in _ops(owner)] == ["TO_CONFIRM"]
    # Quien no gestiona producción no ve lo operativo (VIEWER solo mira el tablero).
    assert _ops(logged_in(world.members[Role.VIEWER])) == []
    # Y otra organización no ve nada de esta.
    other = build_org("b")
    assert _ops(logged_in(other.members[Role.OWNER])) == []
