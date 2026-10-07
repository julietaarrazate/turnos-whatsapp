"""Rentabilidad del evento y presupuestado vs real (O-05, O-06): vectores V13 y V14."""

from decimal import Decimal
from typing import Any

from app.core.enums import Role
from app.modules.finance.profitability import deviation, result
from tests.finance.test_expenses import _add, _url
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok
from tests.security.harness import build_org, logged_in


def test_v13_budget_vs_actual() -> None:
    # DOMAIN_MODEL §5.8 V13: 1.150.000 presupuestado vs 1.210.000 real.
    assert deviation(Decimal("1150000"), Decimal("1210000")) == (
        Decimal("60000"),
        Decimal("0.052174"),  # +5,22 %
    )
    # El proveedor: 500.000 → 520.000 = +4,00 %.
    assert deviation(Decimal("500000"), Decimal("520000"))[1] == Decimal("0.040000")
    assert deviation(Decimal(0), Decimal("100")) == (Decimal("100"), None)


def test_v14_actual_margin() -> None:
    # Margen estimado 28 % sobre C = 1.150.000 → N = 1.597.222,22; con C real 1.210.000 el
    # margen real es 24,24 % (el brief decía 24,1 %).
    sale = Decimal("1597222.22")
    estimated = result(sale, Decimal("1150000"), Decimal(0))
    assert estimated.margin == Decimal("0.280000")
    actual = result(sale, Decimal("1210000"), Decimal(0))
    assert actual.profit == Decimal("387222.22")
    assert actual.margin == Decimal("0.242435")
    assert result(Decimal(0), Decimal(10), Decimal(0)).margin is None


def _get(client: Any, world: Any) -> dict[str, Any]:
    return _ok(client.get(f"/api/v1/events/{world.ids['event_id']}/profitability"))


def test_estimated_vs_actual_and_closing() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    before = _get(owner, world)
    assert (before["estimated"], before["actual"]) == (None, None)  # sin presupuesto aprobado

    _approved(world)  # baseline: costo 1.000 (Producto ejemplo) + 500 (Catering propio)
    data = _get(owner, world)
    estimated, actual = data["estimated"], data["actual"]
    assert estimated["cost"] == "1500.00"
    assert actual["sale_net"] == estimated["sale_net"]
    assert actual["sale_charges"] == estimated["sale_charges"]
    # El harness trae un gasto de 1.000 sin vincular.
    assert actual["cost"] == "1000.00"
    sale, charges = Decimal(actual["sale_net"]), Decimal(actual["sale_charges"])
    assert Decimal(actual["profit"]) == sale - Decimal(1000) - charges
    assert (data["cost_delta"], data["cost_delta_rate"]) == ("-500.00", "-0.333333")
    assert data["final"] is False

    line = next(
        ln for ln in _ok(owner.get(_url(world)))["lines"] if ln["name"] == "Producto ejemplo"
    )
    _ok(_add(owner, world, description="Factura", amount="1452", line_key=line["line_key"]), 201)
    expenses = _ok(owner.get(_url(world)))
    by_supplier = {r["label"]: r for r in expenses["by_supplier"]}
    assert (
        by_supplier["Proveedor ejemplo"]["budgeted"],
        by_supplier["Proveedor ejemplo"]["actual"],
    ) == (
        "1000.00",
        "1200.00",
    )
    assert by_supplier["Sin proveedor"]["budgeted"] == "500.00"  # Catering propio
    by_category = {r["label"]: r for r in expenses["by_category"]}
    assert by_category["Categoría con productos"]["actual"] == "1200.00"
    assert by_category["Categoría vacía"]["budgeted"] == "0.00"  # el gasto no presupuestado
    assert expenses["by_category"][-1]["label"] == "Sin categoría"  # Catering, al final

    base = f"/api/v1/events/{world.ids['event_id']}"
    _ok(owner.post(f"{base}/start-production"))
    _ok(owner.post(f"{base}/complete"))
    _ok(owner.post(f"{base}/close"))
    closed = _get(owner, world)
    assert closed["final"] is True
    assert closed["actual"]["cost"] == "2200.00"
    assert closed["expenses_count"] == 2


def test_cancelled_event_still_takes_cancellation_costs() -> None:
    world = build_org("a")
    _approved(world)
    owner = logged_in(world.members[Role.OWNER])
    cancel = owner.post(
        f"/api/v1/events/{world.ids['event_id']}/status",
        json={"to_status": "CANCELLED", "reason": "El cliente suspendió"},
    )
    assert cancel.status_code == 200, cancel.text
    body = {
        "description": "Seña perdida",
        "amount": "300",
        "category_id": str(world.ids["category_id"]),
    }
    _ok(_add(owner, world, **body), 201)


def test_margins_need_margin_view() -> None:
    world = build_org("a")
    _approved(world)
    production = logged_in(world.members[Role.PRODUCTION])  # ve costos, no márgenes
    assert (
        production.get(f"/api/v1/events/{world.ids['event_id']}/profitability").status_code == 403
    )
    assert production.get(_url(world)).status_code == 200
