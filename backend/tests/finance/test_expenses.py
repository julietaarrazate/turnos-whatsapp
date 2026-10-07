"""Gastos reales y presupuestado vs real (O-04, D-21, journey J6)."""

from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in


def _url(world: OrgWorld) -> str:
    return f"/api/v1/events/{world.ids['event_id']}/expenses"


def _add(client: TestClient, world: OrgWorld, key: str | None = None, **body: Any) -> Any:
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(_url(world), json=body, headers=headers)


def _row(data: dict[str, Any], label: str) -> dict[str, Any]:
    return next(r for r in data["comparison"] if r["label"] == label)


def test_expense_on_a_budget_line_shows_budgeted_vs_actual() -> None:
    world = build_org("a")
    _approved(world)  # baseline: "Producto ejemplo" (costo 1.000) y "Catering propio" (500)
    production = logged_in(world.members[Role.PRODUCTION])
    data = _ok(production.get(_url(world)))
    assert data["has_baseline"] is True
    assert data["editable"] is True
    line = next(ln for ln in data["lines"] if ln["name"] == "Producto ejemplo")
    assert (line["budgeted"], line["supplier_name"]) == ("1000.00", "Proveedor ejemplo")
    assert line["section"]

    # El comprobante dice 1.452 con IVA: para un RI el costo es 1.200 (el IVA es crédito).
    data = _ok(
        _add(
            production,
            world,
            "gasto-1",
            description="Factura proveedor",
            amount="1452",
            line_key=line["line_key"],
        ),
        201,
    )
    [expense] = [e for e in data["items"] if e["description"] == "Factura proveedor"]
    assert expense["amount_base"] == "1200.00"
    assert expense["supplier_name"] == "Proveedor ejemplo"  # sale de la línea
    assert expense["line_name"] == "Producto ejemplo"
    row = _row(data, "Producto ejemplo")
    assert (row["budgeted"], row["actual"], row["delta"], row["delta_rate"]) == (
        "1000.00",
        "1200.00",
        "200.00",
        "0.200000",
    )

    # Reintentar con la misma clave (señal mala en campo) no lo duplica.
    again = _ok(
        _add(
            production,
            world,
            "gasto-1",
            description="Factura proveedor",
            amount="1452",
            line_key=line["line_key"],
        ),
        201,
    )
    assert len([e for e in again["items"] if e["description"] == "Factura proveedor"]) == 1
    # El del harness (sin vincular) más este.
    assert data["actual_total"] == "2200.00"


def test_unbudgeted_expense_needs_a_category() -> None:
    world = build_org("a")
    _approved(world)
    production = logged_in(world.members[Role.PRODUCTION])
    missing = _add(production, world, description="Hielo", amount="5000")
    assert (missing.status_code, missing.json()["code"]) == (422, "expense_needs_line_or_category")
    data = _ok(
        _add(
            production,
            world,
            description="Hielo",
            amount="5000",
            amount_includes_iva=False,
            category_id=str(world.ids["category_id"]),
        ),
        201,
    )
    row = _row(data, "No presupuestado · Categoría vacía")
    assert (row["budgeted"], row["actual"]) == (None, "6000.00")  # 5.000 + 1.000 del harness

    bad_line = _add(
        production,
        world,
        description="X",
        amount="1",
        line_key="00000000-0000-0000-0000-000000000000",
    )
    assert (bad_line.status_code, bad_line.json()["code"]) == (422, "expense_line_not_found")


def test_dollar_expense_uses_the_rate_and_can_be_edited_and_deleted() -> None:
    world = build_org("a")
    _approved(world)
    manager = logged_in(world.members[Role.MANAGER])
    category = str(world.ids["category_id"])
    no_rate = _add(
        manager, world, description="Licencia", amount="100", currency="USD", category_id=category
    )
    assert (no_rate.status_code, no_rate.json()["code"]) == (422, "fx_rate_required")
    data = _ok(
        _add(
            manager,
            world,
            description="Licencia",
            amount="100",
            currency="USD",
            fx_rate="1450.5",
            amount_includes_iva=False,
            category_id=category,
        ),
        201,
    )
    expense = next(e for e in data["items"] if e["description"] == "Licencia")
    assert (expense["fx_rate"], expense["amount_base"]) == ("1450.500000", "145050.00")

    edited = _ok(manager.patch(f"/api/v1/expenses/{expense['id']}", json={"amount": "200"}))
    expense = next(e for e in edited["items"] if e["description"] == "Licencia")
    assert expense["amount_base"] == "290100.00"  # mismo tipo de cambio
    pesos = _ok(manager.patch(f"/api/v1/expenses/{expense['id']}", json={"currency": "ARS"}))
    expense = next(e for e in pesos["items"] if e["description"] == "Licencia")
    assert (expense["fx_rate"], expense["amount_base"]) == ("1.000000", "200.00")

    left = _ok(manager.delete(f"/api/v1/expenses/{expense['id']}"))
    assert all(e["description"] != "Licencia" for e in left["items"])


def test_only_approved_and_open_events_take_expenses() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    body = {"description": "Seña", "amount": "100", "category_id": str(world.ids["category_id"])}
    early = _add(owner, world, **body)
    assert (early.status_code, early.json()["code"]) == (409, "event_not_approved")

    _approved(world)
    base = f"/api/v1/events/{world.ids['event_id']}"
    _ok(owner.post(f"{base}/start-production"))
    _ok(owner.post(f"{base}/complete"))
    _ok(_add(owner, world, **body), 201)  # realizado: se cargan los últimos gastos
    _ok(owner.post(f"{base}/close"))
    locked = _add(owner, world, **body)
    assert (locked.status_code, locked.json()["code"]) == (409, "event_locked")
    assert _ok(owner.get(_url(world)))["editable"] is False


def test_permissions() -> None:
    world = build_org("a")
    _approved(world)
    viewer = logged_in(world.members[Role.VIEWER])
    assert viewer.get(_url(world)).status_code == 403  # los gastos son costos
    quoter = logged_in(world.members[Role.QUOTER])
    assert quoter.get(_url(world)).status_code == 200
    denied = _add(
        quoter, world, description="X", amount="1", category_id=str(world.ids["category_id"])
    )
    assert denied.status_code == 403  # cotizar no es cargar gastos
