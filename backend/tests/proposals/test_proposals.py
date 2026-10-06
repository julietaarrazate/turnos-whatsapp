from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.modules.catalog import today_ar
from tests.conftest import make_client
from tests.security.harness import OrgWorld, build_org, logged_in

Json = dict[str, Any]
FORBIDDEN_KEYS = ("cost", "markup", "margin", "profit", "supplier", "internal", "notes")


def yesterday_ar() -> date:
    """Ayer en Argentina: la vigencia se compara con la fecha local, no con la UTC de la DB."""
    return today_ar() - timedelta(days=1)


def _ok(response: Any, status: int = 200) -> Json:
    assert response.status_code == status, response.text
    return cast(Json, response.json())


def _send(client: TestClient, world: OrgWorld, **body: Any) -> Json:
    budget = _ok(client.get(f"/api/v1/budgets/{world.ids['budget_id']}"))
    return _ok(
        client.post(
            f"/api/v1/budgets/{world.ids['budget_id']}/proposals",
            json=body,
            headers={"If-Match": str(budget["version"]["lock_version"])},
        ),
        201,
    )


def _public(path: str) -> Any:
    token = path.removeprefix("/p/")
    return make_client().get(f"/api/v1/public/proposals/{token}")


def _walk(value: Any, path: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        return [
            item
            for k, v in value.items()
            for item in [(f"{path}.{k}", k), *_walk(v, f"{path}.{k}")]
        ]
    if isinstance(value, list):
        return [item for i, v in enumerate(value) for item in _walk(v, f"{path}[{i}]")]
    return [(path, value)]


def test_send_freezes_draft_and_public_link_shows_whitelisted_snapshot() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    created = _send(owner, world, display_mode="DETAILED", terms="50 % al confirmar")
    assert created["public_path"].startswith("/p/")
    proposal = created["proposal"]
    assert (proposal["status"], proposal["version_no"]) == ("SENT", 1)
    budget = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}"))
    assert budget["version"]["status"] == "FROZEN"
    # El harness ya envió otro presupuesto de este evento: una segunda propuesta negocia.
    assert budget["event"]["status"] == "NEGOTIATION"

    response = _public(created["public_path"])
    public = _ok(response)
    assert public["status"] == "VIEWED"
    assert public["can_decide"] is True
    snapshot = public["proposal"]
    assert snapshot["organization"]["name"] == "Org a"
    assert snapshot["client"]["name"] == "Cliente ejemplo"
    assert snapshot["terms"] == "50 % al confirmar"
    item = snapshot["sections"][0]["items"][0]
    assert (item["amount"], item["unit_price"]) == ("1400.00", "1400.00")
    assert snapshot["totals"] == {
        "total": "1694.00",
        "subtotal": "1400.00",
        "global_discount": None,
        "net": "1400.00",
        "iva": "294.00",
        "iva_included": None,
    }

    # Caso obligatorio 6: ni claves ni valores internos en lo público.
    for path, value in _walk(response.json()):
        if isinstance(value, str) and path.endswith(f".{value}"):
            assert not any(word in value.lower() for word in FORBIDDEN_KEYS), path
    raw = response.text
    for internal in ("1000.00", "1000.000000", "Proveedor ejemplo", "0.400000"):
        assert internal not in raw

    listed = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}/proposals"))
    assert listed[0]["view_count"] == 1
    assert listed[0]["first_viewed_at"] is not None


def test_new_proposal_supersedes_previous_and_event_negotiates() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    first = _send(owner, world)
    owner.post(f"/api/v1/budgets/{world.ids['budget_id']}/versions", json={})
    second = _send(owner, world)
    assert second["proposal"]["version_no"] == 2

    old = _ok(_public(first["public_path"]))
    assert (old["status"], old["can_decide"]) == ("SUPERSEDED", False)
    statuses = [
        p["status"] for p in _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}/proposals"))
    ]
    assert statuses == ["SENT", "SUPERSEDED"]
    budget = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}"))
    assert budget["event"]["status"] == "NEGOTIATION"


def test_revoked_invalid_and_expired_links() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    created = _send(owner, world)
    assert _public("/p/" + "x" * 43).status_code == 404

    with session_scope(DbContext(organization_id=world.organization_id)) as s:
        s.execute(
            text("UPDATE proposals SET valid_until = :yesterday WHERE id = :id"),
            {"yesterday": yesterday_ar(), "id": created["proposal"]["id"]},
        )
    expired = _ok(_public(created["public_path"]))
    assert (expired["status"], expired["can_decide"]) == ("EXPIRED", False)

    other = _send(owner, world, valid_days=10)
    revoked = owner.post(f"/api/v1/proposals/{other['proposal']['id']}/revoke")
    assert _ok(revoked)["status"] == "REVOKED"
    gone = _public(other["public_path"])
    assert gone.status_code == 410
    assert owner.post(f"/api/v1/proposals/{other['proposal']['id']}/revoke").status_code == 409


def test_display_modes_and_iva_included_add_up() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}"))
    section_id = budget["version"]["sections"][0]["id"]
    budget = _ok(
        owner.post(
            f"/api/v1/budgets/{budget['id']}/draft/lines",
            json={"section_id": section_id, "name": "Flete", "unit_cost_amount": "333.33"},
            headers={"If-Match": str(budget["version"]["lock_version"])},
        ),
        201,
    )
    hidden_line = budget["version"]["sections"][0]["lines"][1]["id"]
    owner.patch(
        f"/api/v1/budgets/{budget['id']}/draft/lines/{hidden_line}",
        json={"show_on_proposal": False},
        headers={"If-Match": str(budget["version"]["lock_version"])},
    )
    created = _send(owner, world, display_mode="DETAILED", iva_display="IVA_INCLUDED")
    snapshot = _ok(_public(created["public_path"]))["proposal"]
    section = snapshot["sections"][0]
    assert len(section["items"]) == 1  # la línea oculta no se lista…
    # …pero su importe suma en la sección, y todo suma el total con IVA exacto.
    assert Decimal(section["total"]) == Decimal(snapshot["totals"]["total"])
    assert snapshot["totals"]["iva_included"] is not None

    owner.post(f"/api/v1/budgets/{budget['id']}/versions", json={})
    totals_only = _send(owner, world, display_mode="TOTAL_ONLY")
    snapshot = _ok(_public(totals_only["public_path"]))["proposal"]
    assert snapshot["sections"][0]["total"] is None
    assert all(item["amount"] is None for item in snapshot["sections"][0]["items"])


def test_send_requires_if_match_for_draft_and_permission() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    missing = owner.post(f"/api/v1/budgets/{world.ids['budget_id']}/proposals", json={})
    assert missing.status_code == 428
    production = logged_in(world.members[Role.PRODUCTION])
    denied = production.post(f"/api/v1/budgets/{world.ids['budget_id']}/proposals", json={})
    assert denied.status_code == 403


def test_link_preview_bots_do_not_count_as_views() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    created = _send(owner, world)
    token = created["public_path"].removeprefix("/p/")
    bot = make_client().get(
        f"/api/v1/public/proposals/{token}",
        headers={"User-Agent": "WhatsApp/2.23.20.0 A"},
    )
    assert _ok(bot)["status"] == "SENT"
    listed = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}/proposals"))
    assert (listed[0]["view_count"], listed[0]["first_viewed_at"]) == (0, None)
