"""Paquetes / plantillas (B-06): ABM e inserción en el presupuesto."""

from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in


def _budget(client: TestClient, world: OrgWorld) -> dict[str, Any]:
    return _ok(client.get(f"/api/v1/budgets/{world.ids['budget_id']}"))


def _insert(client: TestClient, world: OrgWorld, package_id: str, **body: Any) -> Any:
    budget = _budget(client, world)
    return client.post(
        f"/api/v1/budgets/{world.ids['budget_id']}/draft/packages",
        json={"package_id": package_id, **body},
        headers={"If-Match": str(budget["version"]["lock_version"])},
    )


def test_package_crud() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    product = str(world.ids["product_id"])
    created = _ok(
        owner.post(
            "/api/v1/packages",
            json={
                "name": " Stand 6x3 ",
                "description": "Stand corporativo",
                "items": [
                    {"product_id": product, "quantity": "4", "section_title": "Escenario"},
                    {"product_id": product, "days_rule": "FIXED", "fixed_days": 2},
                ],
            },
        ),
        201,
    )
    assert created["name"] == "Stand 6x3"
    assert [i["quantity"] for i in created["items"]] == ["4.0000", "1.0000"]
    assert created["items"][0]["product_name"] == "Producto ejemplo"
    listed = {p["name"]: p for p in _ok(owner.get("/api/v1/packages"))}
    assert listed["Stand 6x3"]["item_count"] == 2

    updated = _ok(
        owner.put(
            f"/api/v1/packages/{created['id']}",
            json={"name": "Stand 6x3", "items": [{"product_id": product, "quantity": "1"}]},
        )
    )
    assert len(updated["items"]) == 1
    duplicate = owner.post(
        "/api/v1/packages", json={"name": "stand 6X3", "items": [{"product_id": product}]}
    )
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "package_name_taken")
    no_days = owner.post(
        "/api/v1/packages",
        json={"name": "Otro", "items": [{"product_id": product, "days_rule": "FIXED"}]},
    )
    assert no_days.status_code == 422
    stranger = str(build_org("b").ids["product_id"])
    foreign = owner.post(
        "/api/v1/packages", json={"name": "Ajeno", "items": [{"product_id": stranger}]}
    )
    assert foreign.status_code == 404

    assert owner.delete(f"/api/v1/packages/{created['id']}").status_code == 204
    assert owner.get(f"/api/v1/packages/{created['id']}").status_code == 404
    # Armar paquetes es del catálogo; un QUOTER no puede.
    quoter = logged_in(world.members[Role.QUOTER])
    assert (
        quoter.post(
            "/api/v1/packages", json={"name": "X", "items": [{"product_id": product}]}
        ).status_code
        == 403
    )


def test_insert_package_creates_editable_lines_and_sections() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    product = str(world.ids["product_id"])
    package = _ok(
        owner.post(
            "/api/v1/packages",
            json={
                "name": "Stand",
                "items": [
                    {"product_id": product, "quantity": "3", "section_title": "Escenario"},
                    {
                        "product_id": product,
                        "quantity": "2",
                        "description_client_override": "Armado y desarme",
                    },
                ],
            },
        ),
        201,
    )
    before = _budget(owner, world)["version"]
    lines_before = sum(len(s["lines"]) for s in before["sections"])

    quoter = logged_in(world.members[Role.QUOTER])  # cotizar alcanza para insertarlo
    after = _ok(_insert(quoter, world, package["id"]), 201)["version"]
    sections = {s["title_client"]: s for s in after["sections"]}
    assert "Escenario" in sections  # la sección del ítem se creó
    [stage_line] = sections["Escenario"]["lines"]
    assert (stage_line["quantity"], stage_line["name_internal"]) == ("3.0000", "Producto ejemplo")
    assert stage_line["cost"]["cost_total"] == "3000.00"  # costo vigente del catálogo (1.000)
    first = after["sections"][0]
    assert any(ln["description_client"] == "Armado y desarme" for ln in first["lines"])
    assert sum(len(s["lines"]) for s in after["sections"]) == lines_before + 2
    assert after["sale_net"] != before["sale_net"]

    # Otra vez: reutiliza la sección "Escenario" (no la duplica).
    again = _ok(_insert(owner, world, package["id"]), 201)["version"]
    assert [s["title_client"] for s in again["sections"]].count("Escenario") == 1


def test_inactive_package_and_lock() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    product = str(world.ids["product_id"])
    package = _ok(
        owner.post(
            "/api/v1/packages",
            json={"name": "Viejo", "is_active": False, "items": [{"product_id": product}]},
        ),
        201,
    )
    inactive = _insert(owner, world, package["id"])
    assert (inactive.status_code, inactive.json()["code"]) == (409, "package_inactive")
    stale = owner.post(
        f"/api/v1/budgets/{world.ids['budget_id']}/draft/packages",
        json={"package_id": str(world.ids["package_id"])},
        headers={"If-Match": "999"},
    )
    assert stale.status_code == 409  # lock optimista
