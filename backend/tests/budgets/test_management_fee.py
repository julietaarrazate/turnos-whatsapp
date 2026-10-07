"""Fee de gestión a nivel versión (paso V2b), como en la planilla de la piloto: un porcentaje
sobre la venta de los ítems que el cliente ve como renglón aparte (docs/product/PILOT_NOTES.md)."""

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from app.modules.proposals.pdf import format_percent, render_html
from app.modules.proposals.public_schemas import PublicSnapshot
from tests.conftest import make_client
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import OrgWorld, build_org, logged_in


def _patch_draft(client: TestClient, world: OrgWorld, **body: Any) -> dict[str, Any]:
    budget = _ok(client.get(f"/api/v1/budgets/{world.ids['budget_id']}"))
    return _ok(
        client.patch(
            f"/api/v1/budgets/{world.ids['budget_id']}/draft",
            json=body,
            headers={"If-Match": str(budget["version"]["lock_version"])},
        )
    )


def _public(created: dict[str, Any]) -> dict[str, Any]:
    token = created["public_path"].removeprefix("/p/")
    return _ok(make_client().get(f"/api/v1/public/proposals/{token}"))["proposal"]


def test_fee_is_added_to_the_net_sale_and_carries_iva() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    # El harness trae una línea: costo 1.000, venta 1.400.
    version = _patch_draft(owner, world, management_fee_rate="0.05")["version"]
    assert version["management_fee_rate"] == "0.050000"
    assert version["sale_subtotal"] == "1400.00"
    assert version["management_fee"] == "70.00"
    assert version["sale_net"] == "1470.00"
    assert version["iva"] == "308.70"
    assert version["total"] == "1778.70"
    # El fee es ganancia (no tiene costo) y paga los cargos sobre la venta como el resto.
    margins = version["margins"]
    assert margins["sale_charges"] == "51.45"  # 3,5 % de 1.470
    assert margins["profit"] == "418.55"  # 1.470 − 1.000 − 51,45

    bad = owner.patch(
        f"/api/v1/budgets/{world.ids['budget_id']}/draft",
        json={"management_fee_rate": "1"},
        headers={"If-Match": "999"},
    )
    assert bad.status_code == 422

    # Se congela con la versión y la nueva versión lo hereda.
    _ok(
        owner.post(
            f"/api/v1/budgets/{world.ids['budget_id']}/draft/freeze",
            json={},
            headers={"If-Match": str(version["lock_version"])},
        )
    )
    draft = _ok(owner.post(f"/api/v1/budgets/{world.ids['budget_id']}/versions", json={}), 201)
    assert draft["version"]["management_fee_rate"] == "0.050000"
    assert draft["version"]["management_fee"] == "70.00"


def test_client_sees_the_fee_as_its_own_row() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    _patch_draft(owner, world, management_fee_rate="0.05")
    totals = _public(_send(owner, world))["totals"]
    assert totals["subtotal"] == "1400.00"
    assert totals["management_fee"] == "70.00"
    assert totals["management_fee_rate"] == "0.05"
    assert totals["net"] == "1470.00"
    assert totals["total"] == "1778.70"

    html = render_html(PublicSnapshot.model_validate(_public(_send(owner, world))))
    assert "Fee de gestión (5 %)" in html


def test_with_iva_included_the_fee_takes_its_share_and_everything_adds_up() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    _patch_draft(owner, world, management_fee_rate="0.05")
    proposal = _public(_send(owner, world, display_mode="DETAILED", iva_display="IVA_INCLUDED"))
    items = [i for s in proposal["sections"] for i in s["items"]]
    assert proposal["totals"]["management_fee"] == "84.70"  # 70 + IVA
    assert proposal["totals"]["total"] == "1778.70"
    assert sum(Decimal(i["amount"]) for i in items) + Decimal("84.70") == Decimal("1778.70")


def test_without_fee_the_snapshot_does_not_change() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    totals = _public(_send(owner, world))["totals"]
    assert totals["management_fee"] is None
    assert totals["management_fee_rate"] is None


def test_format_percent() -> None:
    assert format_percent("0.05") == "5 %"
    assert format_percent("0.125") == "12,5 %"
    assert format_percent(None) == ""
