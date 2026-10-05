from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.domain.pricing import LineInput, LinePricingMode, price_line
from app.modules.auth import TenantContext
from app.modules.catalog import today_ar
from app.modules.pricing import pricing_context
from tests.security.harness import OrgWorld, build_org, logged_in


def _owner(world: OrgWorld) -> Any:
    return logged_in(world.members[Role.OWNER])


def _resolve(client: Any, world: OrgWorld, with_client: bool = False) -> dict[str, Any]:
    params = {"product_id": str(world.ids["product_id"])}
    if with_client:
        params["client_id"] = str(world.ids["client_id"])
    response = client.get("/api/v1/pricing/resolve", params=params)
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def test_new_organization_has_general_markup_and_default_settings() -> None:
    owner = _owner(build_org("a"))
    rules = owner.get("/api/v1/pricing/markup-rules").json()
    assert rules[0]["scope"] == "ORG"
    assert rules[0]["value"] == "0.300000"
    assert owner.get("/api/v1/pricing/settings").json() == {
        "rounding_increment": "0.01",
        "min_margin": None,
        "margin_includes_sale_charges": True,
        "price_staleness_days": 30,
    }


def test_markup_chain_client_product_category_org() -> None:
    world = build_org("a")
    owner = _owner(world)
    # El harness crea una regla de 40 % para la categoría del producto.
    resolved = _resolve(owner, world)
    assert (resolved["source"], resolved["markup"]) == ("CATEGORY", "0.400000")
    assert resolved["source_name"] == "Categoría con productos"
    assert resolved["margin"] == "0.285714"

    # Una regla de producto en modo margen (20 %) se convierte a markup: 0,2 / 0,8 = 25 %.
    rule = owner.put(
        "/api/v1/pricing/markup-rules",
        json={
            "scope": "PRODUCT",
            "scope_id": str(world.ids["product_id"]),
            "mode": "MARGIN",
            "value": "0.2",
        },
    )
    assert rule.status_code == 200, rule.text
    assert rule.json()["effective_markup"] == "0.250000"
    resolved = _resolve(owner, world)
    assert (resolved["source"], resolved["markup"]) == ("PRODUCT", "0.250000")

    # El cliente pisa al producto (D-07).
    owner.put(
        "/api/v1/pricing/markup-rules",
        json={"scope": "CLIENT", "scope_id": str(world.ids["client_id"]), "value": "0.15"},
    )
    resolved = _resolve(owner, world, with_client=True)
    assert (resolved["source"], resolved["markup"]) == ("CLIENT", "0.150000")
    assert resolved["source_name"] == "Cliente ejemplo"

    # Sin reglas específicas, queda la general.
    for r in owner.get("/api/v1/pricing/markup-rules").json():
        if r["scope"] != "ORG":
            assert owner.delete(f"/api/v1/pricing/markup-rules/{r['id']}").status_code == 204
    resolved = _resolve(owner, world, with_client=True)
    assert (resolved["source"], resolved["markup"], resolved["source_id"]) == (
        "ORG",
        "0.300000",
        None,
    )


def test_subcategory_falls_back_to_parent_category_rule() -> None:
    world = build_org("a")
    owner = _owner(world)
    parent = str(world.ids["product_category_id"])
    child = owner.post("/api/v1/categories", json={"name": "Truss", "parent_id": parent}).json()
    owner.patch(f"/api/v1/products/{world.ids['product_id']}", json={"category_id": child["id"]})
    resolved = _resolve(owner, world)
    assert (resolved["source"], resolved["source_id"]) == ("CATEGORY", parent)

    owner.put(
        "/api/v1/pricing/markup-rules",
        json={"scope": "CATEGORY", "scope_id": child["id"], "value": "0.55"},
    )
    resolved = _resolve(owner, world)
    assert (resolved["source_id"], resolved["markup"]) == (child["id"], "0.550000")


def test_rules_are_one_per_scope_and_validated() -> None:
    world = build_org("a")
    other = build_org("b")
    owner = _owner(world)
    body = {"scope": "CATEGORY", "scope_id": str(world.ids["category_id"]), "value": "0.35"}
    first = owner.put("/api/v1/pricing/markup-rules", json=body).json()
    second = owner.put("/api/v1/pricing/markup-rules", json={**body, "value": "0.45"}).json()
    assert first["id"] == second["id"]
    assert second["value"] == "0.450000"

    org_rule = owner.put("/api/v1/pricing/markup-rules", json={"scope": "ORG", "value": "0.25"})
    assert org_rule.json()["value"] == "0.250000"
    deleted = owner.delete(f"/api/v1/pricing/markup-rules/{org_rule.json()['id']}")
    assert deleted.status_code == 409

    foreign = {"scope": "PRODUCT", "scope_id": str(other.ids["product_id"]), "value": "0.5"}
    assert owner.put("/api/v1/pricing/markup-rules", json=foreign).status_code == 404
    without_id = {"scope": "PRODUCT", "value": "0.5"}
    assert owner.put("/api/v1/pricing/markup-rules", json=without_id).status_code == 422
    margin_100 = {**body, "mode": "MARGIN", "value": "1"}
    assert owner.put("/api/v1/pricing/markup-rules", json=margin_100).status_code == 422

    actions = [e["action"] for e in owner.get("/api/v1/audit-logs").json()["items"]]
    assert actions.count("markup_rule.changed") == 3


def test_pricing_settings_update_is_audited_and_shared_with_catalog() -> None:
    world = build_org("a")
    owner = _owner(world)
    response = owner.patch(
        "/api/v1/pricing/settings",
        json={"rounding_increment": "100", "min_margin": "0.18", "price_staleness_days": 7},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "rounding_increment": "100",
        "min_margin": "0.18",
        "margin_includes_sale_charges": True,
        "price_staleness_days": 7,
    }
    # null en un campo obligatorio no lo borra; en min_margin sí (sin margen mínimo).
    kept = owner.patch(
        "/api/v1/pricing/settings", json={"rounding_increment": None, "min_margin": None}
    )
    assert kept.json()["rounding_increment"] == "100"
    assert kept.json()["min_margin"] is None
    assert (
        owner.patch("/api/v1/pricing/settings", json={"rounding_increment": "5"}).status_code == 422
    )

    # El catálogo usa el mismo umbral de antigüedad: el costo del harness (01/01/2026) es viejo.
    product = owner.get(f"/api/v1/products/{world.ids['product_id']}").json()
    assert product["offers"][0]["current_cost"]["stale"] is True

    log = owner.get("/api/v1/audit-logs").json()["items"]
    changes = [e for e in log if e["action"] == "org.pricing_settings_changed"]
    assert changes[-1]["after"]["rounding_increment"] == "100"


def test_sale_charges_crud_and_context() -> None:
    world = build_org("a")
    owner = _owner(world)
    created = owner.post(
        "/api/v1/pricing/sale-charges", json={"name": "Imp. débitos y créditos", "rate": "0.012"}
    )
    assert created.status_code == 201
    duplicate = owner.post("/api/v1/pricing/sale-charges", json={"name": "iibb", "rate": "0.03"})
    assert duplicate.status_code == 409
    assert (
        owner.post("/api/v1/pricing/sale-charges", json={"name": "X", "rate": "1"}).status_code
        == 422
    )

    charges = {c["name"]: c for c in owner.get("/api/v1/pricing/sale-charges").json()}
    assert set(charges) == {"IIBB", "Imp. débitos y créditos"}
    owner.patch(
        f"/api/v1/pricing/sale-charges/{charges['Imp. débitos y créditos']['id']}",
        json={"is_active": False},
    )

    # El contexto del motor toma solo los cargos activos: V07/V08 (IIBB 3,5 %).
    with session_scope(DbContext(organization_id=world.organization_id)) as s:
        ctx = cast(TenantContext, SimpleNamespace(organization_id=world.organization_id))
        pricing = pricing_context(s, ctx, None)
    assert [(c.name, c.rate) for c in pricing.sale_charges] == [("IIBB", Decimal("0.035000"))]
    line = LineInput(
        key="v08",
        quantity=Decimal(1),
        unit_cost=Decimal(100000),
        pricing_mode=LinePricingMode.MARGIN,
        target_margin=Decimal("0.25"),
    )
    assert price_line(line, pricing).sale_list_total == Decimal("139860.14")

    deleted = owner.delete(f"/api/v1/pricing/sale-charges/{charges['IIBB']['id']}")
    assert deleted.status_code == 204
    assert [c["name"] for c in owner.get("/api/v1/pricing/sale-charges").json()] == [
        "Imp. débitos y créditos"
    ]


def test_fx_rates_history_latest_first_and_append_only(migrator_engine: Engine) -> None:
    world = build_org("a")
    quoter = logged_in(world.members[Role.QUOTER])
    today = today_ar()
    for days, rate in ((-3, "1420"), (0, "1450.50"), (-1, "1440")):
        response = quoter.post(
            "/api/v1/pricing/fx-rates",
            json={"rate": rate, "rate_date": (today + timedelta(days=days)).isoformat()},
        )
        assert response.status_code == 201, response.text
    production = logged_in(world.members[Role.PRODUCTION])
    rates = production.get("/api/v1/pricing/fx-rates").json()
    assert [r["rate"] for r in rates] == ["1450.500000", "1440.000000", "1420.000000"]
    assert rates[0]["days_old"] == 0
    assert rates[0]["created_by_name"] == "Persona"
    assert production.post("/api/v1/pricing/fx-rates", json={"rate": "1"}).status_code == 403

    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        session_scope(DbContext(organization_id=world.organization_id)) as s,
    ):
        s.execute(text("UPDATE fx_rates SET rate = 1"))
    with migrator_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.org_id', :org, true)"), {"org": str(world.organization_id)}
        )
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("DELETE FROM fx_rates"))


def test_production_never_sees_markup_or_charges() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    for path in (
        "/api/v1/pricing/markup-rules",
        "/api/v1/pricing/sale-charges",
        "/api/v1/pricing/settings",
    ):
        assert production.get(path).status_code == 403
