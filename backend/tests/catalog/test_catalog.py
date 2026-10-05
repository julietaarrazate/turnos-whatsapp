from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.modules.catalog.costs import today_ar
from tests.security.harness import OrgWorld, build_org, logged_in


def _ids(client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    categories = {c["name"]: c["id"] for c in client.get("/api/v1/categories").json()}
    units = {u["code"]: u["id"] for u in client.get("/api/v1/units").json()}
    return categories, units


def _new_product(client: TestClient, name: str = "Truss 3 m", **extra: Any) -> dict[str, Any]:
    categories, units = _ids(client)
    body = {"name": name, "category_id": categories["Estructura"], "unit_id": units["u"], **extra}
    response = client.post("/api/v1/products", json=body)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _new_supplier(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/suppliers", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


def test_new_organizations_get_default_catalog() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    categories, units = _ids(owner)
    assert {"Gráfica", "Estructura", "Iluminación", "Personal", "Transporte"} <= set(categories)
    assert {"u", "m2", "ml", "dia", "h"} <= set(units)
    suppliers = owner.get("/api/v1/suppliers").json()
    assert suppliers[0]["name"] == "Equipo propio"
    assert suppliers[0]["is_internal"] is True
    internal = owner.delete(f"/api/v1/suppliers/{suppliers[0]['id']}")
    assert internal.status_code == 409


def test_categories_allow_one_level_and_block_delete_when_in_use() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    categories, _ = _ids(owner)
    child = owner.post(
        "/api/v1/categories", json={"name": "Truss", "parent_id": categories["Estructura"]}
    )
    assert child.status_code == 201
    grandchild = owner.post(
        "/api/v1/categories", json={"name": "Truss corto", "parent_id": child.json()["id"]}
    )
    assert grandchild.status_code == 422
    assert owner.post("/api/v1/categories", json={"name": "truss"}).status_code == 409

    _new_product(owner)
    assert owner.delete(f"/api/v1/categories/{categories['Estructura']}").status_code == 409
    assert owner.delete(f"/api/v1/categories/{child.json()['id']}").status_code == 204


def test_who_offers_this_product_sorted_by_cost() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    product = _new_product(owner)
    cheap, pricey, no_cost = (_new_supplier(owner, n) for n in ("Barato", "Caro", "Sin costo"))
    for supplier_id, amount in ((pricey, "90000"), (cheap, "75000.50"), (no_cost, None)):
        body: dict[str, Any] = {"supplier_id": supplier_id}
        if amount:
            body["cost"] = {"amount": amount}
        response = owner.post(f"/api/v1/products/{product['id']}/offers", json=body)
        assert response.status_code == 201, response.text

    offers = owner.get(f"/api/v1/products/{product['id']}").json()["offers"]
    assert [o["supplier_name"] for o in offers] == ["Barato", "Caro", "Sin costo"]
    assert offers[0]["current_cost"]["amount"] == "75000.500000"
    assert offers[0]["current_cost"]["includes_iva"] is False
    # La primera oferta cargada queda como preferida.
    assert [o["supplier_name"] for o in offers if o["is_preferred"]] == ["Caro"]

    again = owner.post(f"/api/v1/products/{product['id']}/offers", json={"supplier_id": cheap})
    assert again.status_code == 409


def test_preferred_offer_is_unique_and_shown_in_list() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    product = _new_product(owner)
    a, b = _new_supplier(owner, "A"), _new_supplier(owner, "B")
    owner.post(f"/api/v1/products/{product['id']}/offers", json={"supplier_id": a})
    detail = owner.post(
        f"/api/v1/products/{product['id']}/offers",
        json={"supplier_id": b, "is_preferred": True, "cost": {"amount": "100"}},
    ).json()
    assert [o["supplier_name"] for o in detail["offers"] if o["is_preferred"]] == ["B"]

    offer_b = next(o for o in detail["offers"] if o["supplier_name"] == "B")
    offer_a = next(o for o in detail["offers"] if o["supplier_name"] == "A")
    inactive = owner.patch(f"/api/v1/offers/{offer_b['id']}", json={"is_active": False})
    assert inactive.json()["is_preferred"] is False
    refused = owner.patch(f"/api/v1/offers/{offer_b['id']}", json={"is_preferred": True})
    assert refused.status_code == 409
    owner.patch(f"/api/v1/offers/{offer_a['id']}", json={"is_preferred": True})

    items = owner.get("/api/v1/products", params={"q": "truss"}).json()["items"]
    assert items[0]["preferred"]["supplier_name"] == "A"
    assert items[0]["preferred"]["current_cost"] is None
    assert items[0]["offers_count"] == 1  # solo las activas


def test_cost_history_current_upcoming_and_staleness() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    product = _new_product(owner)
    supplier = _new_supplier(owner, "Rental")
    detail = owner.post(
        f"/api/v1/products/{product['id']}/offers", json={"supplier_id": supplier}
    ).json()
    offer_id = detail["offers"][0]["id"]
    today = today_ar()
    for days, amount in ((-60, "1000"), (-10, "1200"), (15, "1500")):
        response = owner.post(
            f"/api/v1/offers/{offer_id}/prices",
            json={"amount": amount, "valid_from": (today + timedelta(days=days)).isoformat()},
        )
        assert response.status_code == 201, response.text

    offer = response.json()
    assert offer["current_cost"]["amount"] == "1200.000000"
    assert offer["current_cost"]["days_old"] == 10
    assert offer["current_cost"]["stale"] is False
    assert offer["upcoming_cost"]["amount"] == "1500.000000"

    history = owner.get(f"/api/v1/offers/{offer_id}/prices").json()
    assert [p["amount"] for p in history] == ["1500.000000", "1200.000000", "1000.000000"]
    assert all(p["source"] == "MANUAL" for p in history)

    # Con un umbral de 7 días, el costo de hace 10 días queda desactualizado.
    world_org = owner.get("/api/v1/organization").json()["id"]
    with session_scope(DbContext(organization_id=world_org)) as s:
        s.execute(
            text("UPDATE organizations SET settings = settings || '{\"price_staleness_days\": 7}'")
        )
    offer = owner.get(f"/api/v1/products/{product['id']}").json()["offers"][0]
    assert offer["current_cost"]["stale"] is True


def _world_with_cost() -> OrgWorld:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    owner.post(f"/api/v1/offers/{world.ids['offer_id']}/prices", json={"amount": "2500"})
    return world


def test_costs_are_hidden_without_cost_view() -> None:
    world = _world_with_cost()
    client = logged_in(world.members[Role.VIEWER])
    product = client.get(f"/api/v1/products/{world.ids['product_id']}").json()
    assert product["offers"][0]["current_cost"] is None
    supplier = client.get(f"/api/v1/suppliers/{world.ids['supplier_id']}").json()
    assert supplier["offers"][0]["current_cost"] is None
    items = client.get("/api/v1/products").json()["items"]
    assert all(i["preferred"] is None or i["preferred"]["current_cost"] is None for i in items)
    assert client.get(f"/api/v1/offers/{world.ids['offer_id']}/prices").status_code == 403


def test_production_sees_costs_but_cannot_edit_catalog() -> None:
    world = _world_with_cost()
    production = logged_in(world.members[Role.PRODUCTION])
    product = production.get(f"/api/v1/products/{world.ids['product_id']}").json()
    assert product["offers"][0]["current_cost"]["amount"] == "2500.000000"
    response = production.patch(
        f"/api/v1/products/{world.ids['product_id']}", json={"name": "Otro"}
    )
    assert response.status_code == 403


def test_quoter_sees_costs_but_cannot_change_catalog_or_costs() -> None:
    world = _world_with_cost()
    quoter = logged_in(world.members[Role.QUOTER])
    product = quoter.get(f"/api/v1/products/{world.ids['product_id']}").json()
    assert product["offers"][0]["current_cost"]["amount"] == "2500.000000"
    for response in (
        quoter.post(
            f"/api/v1/products/{world.ids['product_id']}/offers",
            json={"supplier_id": str(world.ids["other_supplier_id"])},
        ),
        quoter.post(f"/api/v1/offers/{world.ids['offer_id']}/prices", json={"amount": "1"}),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "permission_denied"


def test_supplier_detail_lists_offers_and_categories() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    categories, _ = _ids(owner)
    created = owner.post(
        "/api/v1/suppliers",
        json={
            "name": "Luces del Sur",
            "rating": 4,
            "category_ids": [categories["Iluminación"], categories["Técnica (audio y video)"]],
            "contacts": [{"name": "Juan", "phone": "+54 9 11 5555-5555", "is_primary": True}],
        },
    ).json()
    assert len(created["category_ids"]) == 2
    product = _new_product(owner, "Par LED")
    owner.post(f"/api/v1/products/{product['id']}/offers", json={"supplier_id": created["id"]})

    detail = owner.get(f"/api/v1/suppliers/{created['id']}").json()
    assert [o["product_name"] for o in detail["offers"]] == ["Par LED"]
    summary = next(s for s in owner.get("/api/v1/suppliers", params={"q": "luces"}).json())
    assert summary["offers_count"] == 1
    assert set(summary["category_names"]) == {"Iluminación", "Técnica (audio y video)"}

    assert owner.delete(f"/api/v1/suppliers/{created['id']}").status_code == 204
    detail = owner.get(f"/api/v1/products/{product['id']}").json()
    assert detail["offers"][0]["is_active"] is False


def test_products_filter_by_category_and_paginate() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    categories, units = _ids(owner)
    for name in ("Banner", "Vinilo", "Lona"):
        owner.post(
            "/api/v1/products",
            json={"name": name, "category_id": categories["Gráfica"], "unit_id": units["m2"]},
        )
    _new_product(owner, "Inactivo", is_active=False)
    page = owner.get(
        "/api/v1/products", params={"category_id": categories["Gráfica"], "limit": 2}
    ).json()
    assert [p["name"] for p in page["items"]] == ["Banner", "Lona"]
    rest = owner.get(
        "/api/v1/products",
        params={"category_id": categories["Gráfica"], "limit": 2, "cursor": page["next_cursor"]},
    ).json()
    assert [p["name"] for p in rest["items"]] == ["Vinilo"]
    names = [p["name"] for p in owner.get("/api/v1/products").json()["items"]]
    assert "Inactivo" not in names
    all_names = [
        p["name"]
        for p in owner.get("/api/v1/products", params={"include_inactive": True}).json()["items"]
    ]
    assert "Inactivo" in all_names


def test_product_validation() -> None:
    world = build_org("a")
    other = build_org("b")
    owner = logged_in(world.members[Role.OWNER])
    _, units = _ids(owner)
    foreign_category = owner.post(
        "/api/v1/products",
        json={
            "name": "X",
            "category_id": str(other.ids["product_category_id"]),
            "unit_id": units["u"],
        },
    )
    assert foreign_category.status_code == 404
    _new_product(owner, "Pantalla")
    assert (
        owner.post(
            "/api/v1/products",
            json={
                "name": "pantalla",
                "category_id": str(world.ids["category_id"]),
                "unit_id": units["u"],
            },
        ).status_code
        == 409
    )
    response = owner.patch(f"/api/v1/products/{world.ids['product_id']}", json={"name": None})
    assert response.status_code == 422


def test_price_history_is_append_only(migrator_engine: Engine) -> None:
    world = _world_with_cost()
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        session_scope(DbContext(organization_id=world.organization_id)) as s,
    ):
        s.execute(text("UPDATE price_history SET amount = 1"))
    # Ni siquiera el dueño de las tablas puede editar el historial (trigger). Con contexto,
    # porque FORCE RLS también aplica al dueño.
    with migrator_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.org_id', :org, true)"),
            {"org": str(world.organization_id)},
        )
        assert conn.execute(text("SELECT count(*) FROM price_history")).scalar_one() > 0
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("DELETE FROM price_history"))
