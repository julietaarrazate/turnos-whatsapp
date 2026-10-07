"""Reportes de rentabilidad (A-02) e historial comercial del cliente (PRODUCT_SPEC §4.2)."""

from decimal import Decimal
from typing import Any

from app.core.enums import Role
from app.modules.catalog import today_ar
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in


def _range() -> dict[str, str]:
    today = today_ar().isoformat()
    return {"from": today, "to": today}


def _prepare(world: OrgWorld) -> Any:
    _approved(world)
    owner = logged_in(world.members[Role.OWNER])
    _ok(
        owner.patch(
            f"/api/v1/events/{world.ids['event_id']}", json={"start_date": today_ar().isoformat()}
        )
    )
    return owner


def test_profitability_report_by_event_client_and_month() -> None:
    world = build_org("a")
    owner = _prepare(world)
    version = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}"))["version"]

    report = _ok(owner.get("/api/v1/reports/profitability", params=_range()))
    [row] = report["rows"]
    assert row["events"] == 1
    assert row["sale_net"] == version["sale_net"]
    assert row["estimated_cost"] == version["costs"]["cost_direct"]
    assert row["estimated_profit"] == version["margins"]["profit"]
    # El harness trae un gasto de 1.000: hay ganancia real, parcial (no está cerrado).
    assert (row["events_with_costs"], row["actual_cost"]) == (1, "1000.00")
    sale, charges = Decimal(version["sale_net"]), Decimal(version["margins"]["sale_charges"])
    assert Decimal(row["actual_profit"]) == sale - 1000 - charges
    assert row["partial"] is True
    assert report["total"]["sale_net"] == row["sale_net"]

    by_client = _ok(
        owner.get("/api/v1/reports/profitability", params={**_range(), "group": "client"})
    )
    assert by_client["rows"][0]["label"] == "Cliente ejemplo"
    by_month = _ok(
        owner.get("/api/v1/reports/profitability", params={**_range(), "group": "month"})
    )
    assert by_month["rows"][0]["label"] == today_ar().strftime("%Y-%m")

    # Fuera del rango no aparece.
    empty = _ok(
        owner.get(
            "/api/v1/reports/profitability", params={"from": "2020-01-01", "to": "2020-01-31"}
        )
    )
    assert (empty["rows"], empty["total"]["events"]) == ([], 0)

    csv = owner.get("/api/v1/reports/profitability.csv", params=_range())
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    lines = csv.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Grupo;Eventos;Venta neta")
    assert lines[-1].startswith("Total;1;")
    assert "1000,00" in lines[1]  # coma decimal para Excel en español

    bad = owner.get(
        "/api/v1/reports/profitability", params={"from": "2026-02-01", "to": "2026-01-01"}
    )
    assert (bad.status_code, bad.json()["code"]) == (422, "invalid_range")


def test_reports_need_margin_view() -> None:
    world = build_org("a")
    _prepare(world)
    for role in (Role.VIEWER, Role.PRODUCTION):
        client = logged_in(world.members[role])
        assert client.get("/api/v1/reports/profitability", params=_range()).status_code == 403


def test_client_history() -> None:
    world = build_org("a")
    owner = _prepare(world)
    version = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}"))["version"]
    history = _ok(owner.get(f"/api/v1/clients/{world.ids['client_id']}/history"))
    assert (history["budgets"], history["events"], history["accepted"], history["lost"]) == (
        2,
        1,
        1,
        0,
    )
    assert history["conversion"] == "1.000000"
    assert history["billed"] == version["sale_net"]
    assert history["estimated_margin"] == version["margins"]["margin_net"]
    assert history["actual_margin"] is not None

    viewer = logged_in(world.members[Role.VIEWER])
    seen = _ok(viewer.get(f"/api/v1/clients/{world.ids['client_id']}/history"))
    assert (seen["estimated_margin"], seen["actual_margin"], seen["preferential_markup"]) == (
        None,
        None,
        None,
    )
    assert seen["billed"] == version["sale_net"]
