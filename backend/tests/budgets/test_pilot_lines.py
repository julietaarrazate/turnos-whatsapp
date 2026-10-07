"""Líneas como las de la planilla de la piloto: costo por la línea entera y etiquetas
"Bonificado" / "A definir" en la propuesta (docs/product/PILOT_NOTES.md)."""

from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from tests.conftest import make_client
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import OrgWorld, build_org, logged_in


def _budget(client: TestClient, world: OrgWorld) -> dict[str, Any]:
    return _ok(client.get(f"/api/v1/budgets/{world.ids['budget_id']}"))


def _add(client: TestClient, world: OrgWorld, **body: Any) -> dict[str, Any]:
    budget = _budget(client, world)
    return _ok(
        client.post(
            f"/api/v1/budgets/{world.ids['budget_id']}/draft/lines",
            json={"section_id": budget["version"]["sections"][0]["id"], **body},
            headers={"If-Match": str(budget["version"]["lock_version"])},
        ),
        201,
    )


def _line(budget: dict[str, Any], name: str) -> dict[str, Any]:
    lines = budget["version"]["sections"][0]["lines"]
    return next(line for line in lines if line["name_internal"] == name)


def test_cost_quoted_for_the_whole_line() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _add(
        owner,
        world,
        name="Vallas",
        quantity="18",
        unit_cost_amount="500000",
        cost_is_total=True,
    )
    line = _line(budget, "Vallas")
    assert line["cost"]["cost_is_total"] is True
    assert line["cost"]["cost_total"] == "500000.00"  # no 18 × 500.000

    # Volver a costo unitario: ahora sí multiplica.
    updated = _ok(
        owner.patch(
            f"/api/v1/budgets/{world.ids['budget_id']}/draft/lines/{line['id']}",
            json={"cost_is_total": False, "unit_cost_amount": "25000"},
            headers={"If-Match": str(budget["version"]["lock_version"])},
        )
    )
    assert _line(updated, "Vallas")["cost"]["cost_total"] == "450000.00"

    # Es un dato de costo: sin cost.view no se puede tocar.
    viewer = logged_in(world.members[Role.VIEWER])
    denied = viewer.patch(
        f"/api/v1/budgets/{world.ids['budget_id']}/draft/lines/{line['id']}",
        json={"cost_is_total": True},
        headers={"If-Match": str(updated["version"]["lock_version"])},
    )
    assert denied.status_code == 403


def test_bonificado_and_a_definir_show_a_label_instead_of_an_amount() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _add(owner, world, name="Dirección de proyecto", unit_cost_amount="0")
    line = _line(budget, "Dirección de proyecto")
    budget = _ok(
        owner.patch(
            f"/api/v1/budgets/{world.ids['budget_id']}/draft/lines/{line['id']}",
            json={"client_price_label": "BONIFICADO"},
            headers={"If-Match": str(budget["version"]["lock_version"])},
        )
    )
    assert _line(budget, "Dirección de proyecto")["client_price_label"] == "BONIFICADO"
    budget = _add(owner, world, name="Catering", unit_cost_amount="0")
    catering = _line(budget, "Catering")
    _ok(
        owner.patch(
            f"/api/v1/budgets/{world.ids['budget_id']}/draft/lines/{catering['id']}",
            json={"client_price_label": "A_DEFINIR"},
            headers={"If-Match": str(budget["version"]["lock_version"])},
        )
    )
    bad = owner.patch(
        f"/api/v1/budgets/{world.ids['budget_id']}/draft/lines/{catering['id']}",
        json={"client_price_label": "GRATIS"},
        headers={"If-Match": "999"},
    )
    assert bad.status_code == 422

    created = _send(owner, world, display_mode="DETAILED")
    token = created["public_path"].removeprefix("/p/")
    items = _ok(make_client().get(f"/api/v1/public/proposals/{token}"))["proposal"]["sections"][0][
        "items"
    ]
    by_name = {i["description"]: i for i in items}
    assert by_name["Dirección de proyecto"]["price_label"] == "BONIFICADO"
    assert by_name["Dirección de proyecto"]["amount"] is None
    assert by_name["Catering"]["price_label"] == "A_DEFINIR"
    assert by_name["Producto ejemplo"]["price_label"] is None
    assert by_name["Producto ejemplo"]["amount"] == "1400.00"
