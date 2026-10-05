from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from tests.security.harness import OrgWorld, build_org, logged_in

Json = dict[str, Any]


def _ok(response: Any, status: int = 200) -> Json:
    assert response.status_code == status, response.text
    return cast(Json, response.json())


def _draft(client: TestClient, budget: Json, method: str, path: str, **kwargs: Any) -> Any:
    lock = str(budget["version"]["lock_version"])
    return client.request(
        method, f"/api/v1/budgets/{budget['id']}/draft{path}", headers={"If-Match": lock}, **kwargs
    )


def _budget(client: TestClient, world: OrgWorld) -> Json:
    return _ok(client.get(f"/api/v1/budgets/{world.ids['budget_id']}"))


def _line(budget: Json) -> Json:
    return cast(Json, budget["version"]["sections"][0]["lines"][0])


def test_new_budget_creates_event_and_client_inline_and_is_idempotent() -> None:
    world = build_org("a")
    quoter = logged_in(world.members[Role.QUOTER])
    body = {
        "event": {"client_name": "Banco Andino", "name": "Convención 2027", "event_days": 3},
        "currency": "ARS",
    }
    headers = {"Idempotency-Key": "nuevo-presupuesto-1"}
    first = _ok(quoter.post("/api/v1/budgets", json=body, headers=headers), 201)
    again = _ok(quoter.post("/api/v1/budgets", json=body, headers=headers), 201)
    assert again["id"] == first["id"]
    other = quoter.post("/api/v1/budgets", json={**body, "currency": "USD"}, headers=headers)
    assert other.status_code == 422
    assert other.json()["code"] == "idempotency_key_reused"

    assert first["title"] == "Convención 2027"
    assert first["event"]["client_name"] == "Banco Andino"
    assert first["event"]["status"] == "QUOTING"  # LEAD → QUOTING al crear el presupuesto
    version = first["version"]
    assert (version["version_no"], version["status"]) == (1, "DRAFT")
    assert [s["title_client"] for s in version["sections"]] == ["General"]
    assert version["total"] == "0.00"
    # El harness ya creó dos presupuestos en esta organización (uno enviado).
    assert first["number"] == 3
    events = _ok(quoter.get("/api/v1/events", params={"q": "convención"}))["items"]
    assert [e["number"] for e in events] == [2]


def test_catalog_line_takes_preferred_cost_and_rule_markup() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    line = _line(_budget(owner, world))
    # Costo vigente 1.000 (harness) y regla de su categoría: 40 %.
    assert line["cost"]["unit_cost_amount"] == "1000.000000"
    assert line["cost"]["cost_as_of"] == "2026-01-01"
    assert line["margin"]["rule_source"] == "CATEGORY"
    assert line["margin"]["markup_source"] == "CATEGORY"
    assert line["sale_total"] == "1400.00"
    assert line["supplier_name"] == "Proveedor ejemplo"


def test_every_change_recalculates_and_stale_lock_is_rejected() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    line_id = _line(budget)["id"]

    updated = _ok(_draft(owner, budget, "PATCH", f"/lines/{line_id}", json={"quantity": "3"}))
    assert _line(updated)["sale_total"] == "4200.00"
    assert updated["version"]["sale_subtotal"] == "4200.00"
    assert updated["version"]["iva"] == "882.00"  # RI: 21 %
    assert updated["version"]["total"] == "5082.00"
    assert updated["version"]["lock_version"] == budget["version"]["lock_version"] + 1

    stale = _draft(owner, budget, "PATCH", f"/lines/{line_id}", json={"quantity": "9"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "budget_version_conflict"
    assert stale.json()["lock_version"] == updated["version"]["lock_version"]
    assert _line(_budget(owner, world))["quantity"] == "3.0000"

    quoted = owner.patch(
        f"/api/v1/budgets/{budget['id']}/draft/lines/{line_id}",
        json={"discount_rate": "0.1"},
        headers={"If-Match": f'W/"{updated["version"]["lock_version"]}"'},
    )
    assert _line(_ok(quoted))["sale_total"] == "3780.00"


def test_free_line_manual_markup_and_ignored_computed_fields() -> None:
    world = build_org("a")
    quoter = logged_in(world.members[Role.QUOTER])
    budget = _budget(quoter, world)
    section_id = budget["version"]["sections"][0]["id"]
    added = _ok(
        _draft(
            quoter,
            budget,
            "POST",
            "/lines",
            json={
                "section_id": section_id,
                "name": "Flete",
                "unit_cost_amount": "50000",
                "sale_total": "1",  # I8: los importes calculados que manda el cliente se ignoran
            },
        ),
        201,
    )
    free = added["version"]["sections"][0]["lines"][1]
    assert free["margin"]["rule_source"] == "ORG"
    assert free["sale_total"] == "65000.00"  # 50.000 × 1,30
    assert free["cost"]["cost_as_of"] is None

    manual = _ok(
        _draft(quoter, added, "PATCH", f"/lines/{free['id']}", json={"markup_manual": "0.5"})
    )
    line = manual["version"]["sections"][0]["lines"][1]
    assert (line["sale_total"], line["margin"]["markup_source"]) == ("75000.00", "LINE")


def test_target_price_mode_reaches_exact_net() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    section_id = budget["version"]["sections"][0]["id"]
    budget = _ok(
        _draft(
            owner,
            budget,
            "POST",
            "/lines",
            json={"section_id": section_id, "name": "Personal", "unit_cost_amount": "2900"},
        ),
        201,
    )
    priced = _ok(
        _draft(owner, budget, "PATCH", "", json={"pricing_mode": "PRICE", "target_price": "5000"})
    )
    version = priced["version"]
    assert version["sale_net"] == "5000.00"
    assert version["margins"]["profit"] == str(
        Decimal("5000.00") - Decimal("3900.00") - Decimal("175.00")
    )
    # IIBB 3,5 % del harness: 5.000 × 0,035 = 175.
    assert version["margins"]["sale_charges_detail"] == [
        {"name": "IIBB", "rate": "0.035000", "amount": "175.00"}
    ]

    # Por debajo del costo: se puede, con aviso.
    cheap = _ok(_draft(owner, priced, "PATCH", "", json={"target_price": "3000"}))
    assert cheap["version"]["sale_net"] == "3000.00"
    assert "below_cost" in cheap["version"]["warnings"]

    # Con la primera línea bloqueada (1.400), el objetivo no puede ser menor.
    first = cheap["version"]["sections"][0]["lines"][0]["id"]
    locked = _ok(_draft(owner, cheap, "PATCH", f"/lines/{first}", json={"is_locked": True}))
    invalid = _draft(owner, locked, "PATCH", "", json={"target_price": "1000"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "pricing_target_below_locked"


def test_redaction_by_role() -> None:
    world = build_org("a")
    viewer = _budget(logged_in(world.members[Role.VIEWER]), world)
    assert _line(viewer)["cost"] is None
    assert _line(viewer)["margin"] is None
    assert viewer["version"]["costs"] is None
    assert viewer["version"]["margins"] is None
    assert _line(viewer)["sale_total"] == "1400.00"

    production = _budget(logged_in(world.members[Role.PRODUCTION]), world)
    assert _line(production)["cost"]["cost_total"] == "1000.00"
    assert _line(production)["margin"] is None
    assert production["version"]["margins"] is None


def test_rule_changes_do_not_touch_existing_drafts() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    owner.put(
        "/api/v1/pricing/markup-rules",
        json={
            "scope": "CATEGORY",
            "scope_id": str(world.ids["product_category_id"]),
            "value": "0.9",
        },
    )
    owner.post("/api/v1/pricing/sale-charges", json={"name": "Comisión", "rate": "0.05"})
    budget = _budget(owner, world)
    line_id = _line(budget)["id"]
    updated = _ok(_draft(owner, budget, "PATCH", f"/lines/{line_id}", json={"quantity": "2"}))
    assert _line(updated)["sale_total"] == "2800.00"  # sigue con el 40 % del alta
    assert [c["name"] for c in updated["version"]["margins"]["sale_charges_detail"]] == ["IIBB"]


def test_freeze_new_version_and_immutability() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    frozen = _ok(_draft(owner, budget, "POST", "/freeze", json={"change_note": "Primera"}))
    assert frozen["version"]["status"] == "FROZEN"
    assert frozen["version"]["change_note"] == "Primera"

    line_id = _line(frozen)["id"]
    blocked = _draft(owner, frozen, "PATCH", f"/lines/{line_id}", json={"quantity": "2"})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "budget_no_draft"
    with (
        pytest.raises(DBAPIError, match="congelada"),
        session_scope(DbContext(organization_id=world.organization_id)) as s,
    ):
        s.execute(text("UPDATE budget_lines SET quantity = 5"))

    v2 = _ok(owner.post(f"/api/v1/budgets/{budget['id']}/versions", json={}), 201)
    assert (v2["version"]["version_no"], v2["version"]["status"]) == (2, "DRAFT")
    assert _line(v2)["line_key"] == _line(frozen)["line_key"]
    assert _line(v2)["id"] != line_id
    assert owner.post(f"/api/v1/budgets/{budget['id']}/versions", json={}).status_code == 409

    discarded = _ok(_draft(owner, v2, "DELETE", ""))
    assert [v["status"] for v in discarded["versions"]] == ["FROZEN"]
    old = _ok(owner.get(f"/api/v1/budgets/{budget['id']}/versions/1"))
    assert old["version"]["total"] == frozen["version"]["total"]


def test_sections_and_moving_lines() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    general = budget["version"]["sections"][0]["id"]
    budget = _ok(_draft(owner, budget, "POST", "/sections", json={"title_client": "Técnica"}), 201)
    tecnica = budget["version"]["sections"][1]["id"]
    line_id = _line(budget)["id"]
    moved = _ok(_draft(owner, budget, "PATCH", f"/lines/{line_id}", json={"section_id": tecnica}))
    sections = {s["title_client"]: s for s in moved["version"]["sections"]}
    assert sections["General"]["lines"] == []
    assert sections["Técnica"]["sale_total"] == "1400.00"

    reordered = _ok(_draft(owner, moved, "PATCH", f"/sections/{tecnica}", json={"position": 0}))
    assert [s["title_client"] for s in reordered["version"]["sections"]] == ["Técnica", "General"]
    deleted = _ok(_draft(owner, reordered, "DELETE", f"/sections/{tecnica}"))
    assert [s["id"] for s in deleted["version"]["sections"]] == [general]
    assert deleted["version"]["total"] == "0.00"
    last = _draft(owner, deleted, "DELETE", f"/sections/{general}")
    assert last.status_code == 409


def test_usd_budget_needs_fx_and_presents_converted_totals() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    missing = _draft(owner, budget, "PATCH", "", json={"currency": "USD"})
    assert missing.status_code == 422
    assert missing.json()["code"] == "fx_rate_required"

    owner.post("/api/v1/pricing/fx-rates", json={"rate": "1400"})
    usd = _ok(_draft(owner, budget, "PATCH", "", json={"currency": "USD"}))
    assert usd["currency"] == "USD"
    assert usd["version"]["fx"]["rate"] == "1400.000000"
    presentation = usd["version"]["presentation"]
    assert presentation["subtotal"] == "1.00"  # 1.400 / 1.400
    assert presentation["total"] == "1.21"


def test_event_status_transitions() -> None:
    world = build_org("a")
    manager = logged_in(world.members[Role.MANAGER])
    event_id = world.ids["event_id"]
    no_reason = manager.post(f"/api/v1/events/{event_id}/status", json={"to_status": "LOST"})
    assert no_reason.status_code == 422
    lost = _ok(
        manager.post(
            f"/api/v1/events/{event_id}/status",
            json={"to_status": "LOST", "reason": "Eligió otra productora"},
        )
    )
    assert (lost["status"], lost["lost_reason"]) == ("LOST", "Eligió otra productora")
    blocked = manager.post("/api/v1/budgets", json={"event_id": str(event_id)})
    assert blocked.status_code == 409
    invalid = manager.post(
        f"/api/v1/events/{event_id}/status", json={"to_status": "CANCELLED", "reason": "x"}
    )
    assert invalid.status_code == 409

    reopened = _ok(manager.post(f"/api/v1/events/{event_id}/status", json={"to_status": "QUOTING"}))
    assert reopened["status"] == "QUOTING"
    # El harness ya envió una propuesta de este evento (QUOTING → SENT).
    history = [h["to_status"] for h in reopened["history"]]
    assert history == ["LEAD", "QUOTING", "SENT", "LOST", "QUOTING"]


def test_event_update_and_listing_filters() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    event_id = world.ids["event_id"]
    bad = owner.patch(
        f"/api/v1/events/{event_id}", json={"start_date": "2027-03-10", "end_date": "2027-03-01"}
    )
    assert bad.status_code == 422
    updated = _ok(
        owner.patch(f"/api/v1/events/{event_id}", json={"venue": "La Rural", "event_days": 2})
    )
    assert (updated["venue"], updated["event_days"]) == ("La Rural", 2)

    for name in ("Fiesta fin de año", "Lanzamiento"):
        owner.post("/api/v1/events", json={"client_id": str(world.ids["client_id"]), "name": name})
    leads = _ok(owner.get("/api/v1/events", params={"status": "LEAD"}))["items"]
    assert {e["name"] for e in leads} == {"Fiesta fin de año", "Lanzamiento"}
    page = _ok(owner.get("/api/v1/events", params={"limit": 2}))
    rest = _ok(owner.get("/api/v1/events", params={"limit": 2, "cursor": page["next_cursor"]}))
    names = [e["name"] for e in page["items"] + rest["items"]]
    assert names == ["Lanzamiento", "Fiesta fin de año", "Evento ejemplo"]

    budgets = _ok(owner.get("/api/v1/budgets", params={"event_id": str(event_id)}))["items"]
    by_id = {b["id"]: b for b in budgets}
    assert len(by_id) == 2  # el borrador y el enviado del harness
    assert by_id[str(world.ids["budget_id"])]["sale_net"] == "1400.00"


def _record_cost(client: TestClient, world: OrgWorld, amount: str) -> None:
    _ok(client.post(f"/api/v1/offers/{world.ids['offer_id']}/prices", json={"amount": amount}), 201)


def test_refresh_costs_preview_and_apply() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    empty = _ok(owner.get(f"/api/v1/budgets/{budget['id']}/draft/refresh-costs"))
    assert empty["changes"] == []

    _record_cost(owner, world, "1500")
    preview = _ok(owner.get(f"/api/v1/budgets/{budget['id']}/draft/refresh-costs"))
    change = preview["changes"][0]
    assert (change["old_unit_cost"], change["new_unit_cost"]) == ("1000.000000", "1500.000000")
    assert change["amount_changed"] is True
    assert (preview["totals"]["sale_net_before"], preview["totals"]["sale_net_after"]) == (
        "1400.00",
        "2100.00",
    )
    # La vista previa no cambia nada.
    assert _line(_budget(owner, world))["sale_total"] == "1400.00"

    applied = _ok(_draft(owner, budget, "POST", "/refresh-costs", json={}))
    assert _line(applied)["sale_total"] == "2100.00"
    assert _line(applied)["cost"]["cost_as_of"] is not None
    again = _ok(owner.get(f"/api/v1/budgets/{budget['id']}/draft/refresh-costs"))
    assert again["changes"] == []


def test_refresh_costs_only_selected_lines() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    _record_cost(owner, world, "1500")
    untouched = _ok(_draft(owner, budget, "POST", "/refresh-costs", json={"line_ids": []}))
    assert _line(untouched)["sale_total"] == "1400.00"


def test_reapply_rules_updates_markups_and_charges() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    owner.put(
        "/api/v1/pricing/markup-rules",
        json={
            "scope": "CATEGORY",
            "scope_id": str(world.ids["product_category_id"]),
            "value": "0.5",
        },
    )
    owner.post("/api/v1/pricing/sale-charges", json={"name": "Comisión", "rate": "0.05"})
    budget = _budget(owner, world)
    preview = _ok(owner.get(f"/api/v1/budgets/{budget['id']}/draft/reapply-rules"))
    change = preview["changes"][0]
    assert (change["old_markup"], change["new_markup"]) == ("0.400000", "0.500000")
    assert [c["name"] for c in preview["charges_after"]] == ["Comisión", "IIBB"]
    assert preview["totals"]["sale_net_after"] == "1500.00"

    applied = _ok(_draft(owner, budget, "POST", "/reapply-rules", json={}))
    assert _line(applied)["sale_total"] == "1500.00"
    charges = [c["name"] for c in applied["version"]["margins"]["sale_charges_detail"]]
    assert charges == ["Comisión", "IIBB"]

    production = logged_in(world.members[Role.PRODUCTION])
    assert production.get(f"/api/v1/budgets/{budget['id']}/draft/reapply-rules").status_code == 403


def test_duplicate_to_new_event_with_current_costs_and_days() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    line_id = _line(budget)["id"]
    budget = _ok(
        _draft(owner, budget, "PATCH", f"/lines/{line_id}", json={"charge_mode": "PER_DAY"})
    )
    _record_cost(owner, world, "2000")

    copy = _ok(
        owner.post(
            f"/api/v1/budgets/{budget['id']}/duplicate",
            json={"event": {"client_name": "Otro cliente", "name": "Gira", "event_days": 3}},
        ),
        201,
    )
    assert copy["costs_changed"] == 1
    duplicated = copy["budget"]
    assert duplicated["id"] != budget["id"]
    assert duplicated["event"]["client_name"] == "Otro cliente"
    line = _line(duplicated)
    assert line["line_key"] != _line(budget)["line_key"]
    assert line["days"] == 3  # usaba los días del evento original (1) → los del nuevo
    assert line["cost"]["unit_cost_amount"] == "2000.000000"
    assert line["sale_total"] == "8400.00"  # 2.000 × 3 días × 1,40
    # El original no cambia.
    assert _line(_budget(owner, world))["sale_total"] == "1400.00"


def test_compare_versions_by_line_key() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _budget(owner, world)
    section_id = budget["version"]["sections"][0]["id"]
    budget = _ok(
        _draft(
            owner,
            budget,
            "POST",
            "/lines",
            json={"section_id": section_id, "name": "Flete", "unit_cost_amount": "1000"},
        ),
        201,
    )
    v1 = _ok(_draft(owner, budget, "POST", "/freeze", json={}))
    v2 = _ok(owner.post(f"/api/v1/budgets/{budget['id']}/versions", json={}), 201)
    lines = v2["version"]["sections"][0]["lines"]
    truss = next(ln for ln in lines if ln["name_internal"] == "Producto ejemplo")
    flete = next(ln for ln in lines if ln["name_internal"] == "Flete")
    v2 = _ok(_draft(owner, v2, "PATCH", f"/lines/{truss['id']}", json={"quantity": "2"}))
    v2 = _ok(_draft(owner, v2, "DELETE", f"/lines/{flete['id']}"))
    v2 = _ok(
        _draft(
            owner,
            v2,
            "POST",
            "/lines",
            json={
                "section_id": v2["version"]["sections"][0]["id"],
                "name": "Seguridad",
                "unit_cost_amount": "500",
            },
        ),
        201,
    )

    diff = _ok(owner.get(f"/api/v1/budgets/{budget['id']}/compare", params={"from": 1, "to": 2}))
    assert (diff["added"], diff["removed"], diff["modified"]) == (1, 1, 1)
    by_name = {d["name"]: d for d in diff["lines"]}
    assert by_name["Seguridad"]["kind"] == "ADDED"
    assert by_name["Flete"]["kind"] == "REMOVED"
    modified = by_name["Producto ejemplo"]
    fields = {c["field"]: (c["before"], c["after"]) for c in modified["changes"]}
    assert fields["quantity"] == ("1", "2")
    assert fields["sale_total"] == ("1400", "2800")
    assert diff["sale_net_before"] == v1["version"]["sale_net"]
    assert diff["margin_delta_points"] is not None

    viewer = logged_in(world.members[Role.VIEWER])
    hidden = _ok(viewer.get(f"/api/v1/budgets/{budget['id']}/compare", params={"from": 1, "to": 2}))
    assert hidden["cost_before"] is None
    assert hidden["profit_before"] is None
    assert all(
        c["field"] not in {"unit_cost_amount", "markup_applied"}
        for d in hidden["lines"]
        for c in d["changes"]
    )
    missing = owner.get(f"/api/v1/budgets/{budget['id']}/compare", params={"from": 1, "to": 9})
    assert missing.status_code == 404
