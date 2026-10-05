import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from tests.security.harness import build_org, logged_in


def test_viewer_financial_visibility_is_configurable() -> None:
    world = build_org("a")
    viewer = logged_in(world.members[Role.VIEWER])
    assert "margin.view" not in viewer.get("/api/v1/auth/me").json()["permissions"]

    admin = logged_in(world.members[Role.ADMIN])
    response = admin.patch("/api/v1/organization", json={"viewer_sees_financials": True})
    assert response.status_code == 200
    assert response.json()["viewer_sees_financials"] is True

    permissions = viewer.get("/api/v1/auth/me").json()["permissions"]
    assert {"cost.view", "margin.view"} <= set(permissions)


def test_fiscal_data_only_for_owner_and_validates_cuit() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    bad = owner.patch("/api/v1/organization/fiscal", json={"tax_id": "123"})
    assert bad.status_code == 422
    ok = owner.patch(
        "/api/v1/organization/fiscal",
        json={"tax_id": "30-71234567-1", "tax_condition": "MONOTRIBUTO", "legal_name": "Prod SA"},
    )
    assert ok.status_code == 200
    assert ok.json()["tax_condition"] == "MONOTRIBUTO"
    actions = [e["action"] for e in owner.get("/api/v1/audit-logs").json()["items"]]
    assert "org.fiscal_changed" in actions


def test_audit_log_pagination_is_newest_first() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    for name in ("Uno", "Dos", "Tres"):
        owner.patch("/api/v1/organization", json={"name": name})
    first = owner.get("/api/v1/audit-logs", params={"limit": 2}).json()
    assert [e["after"]["name"] for e in first["items"]] == ["Tres", "Dos"]
    assert first["next_cursor"]
    second = owner.get(
        "/api/v1/audit-logs", params={"limit": 2, "before": first["next_cursor"]}
    ).json()
    assert [
        e["after"]["name"] for e in second["items"] if e["action"] == "org.settings_changed"
    ] == ["Uno"]


def test_audit_log_is_append_only(migrator_engine: Engine) -> None:
    world = build_org("a")
    logged_in(world.members[Role.OWNER]).patch("/api/v1/organization", json={"name": "X"})

    # El rol de la aplicación no tiene permiso de UPDATE/DELETE...
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        session_scope(DbContext(organization_id=world.organization_id)) as s,
    ):
        s.execute(text("UPDATE audit_logs SET action = 'x'"))
    # ...y ni siquiera el dueño del esquema puede modificar filas (trigger). FORCE RLS también
    # aplica al dueño: sin contexto no vería filas y el DELETE no tocaría nada.
    with migrator_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.org_id', :org, true)"),
            {"org": str(world.organization_id)},
        )
        assert conn.execute(text("SELECT count(*) FROM audit_logs")).scalar_one() > 0
        with pytest.raises(DBAPIError, match="append-only"):
            conn.execute(text("DELETE FROM audit_logs"))


def test_requests_without_active_org_are_rejected() -> None:
    world = build_org("a")
    client = logged_in(world.members[Role.OWNER])
    with session_scope(DbContext(organization_id=world.organization_id)) as s:
        s.execute(text("UPDATE memberships SET status = 'DISABLED' WHERE role = 'OWNER'"))
    # Re-login sin membresías activas: no hay organización activa.
    client.post("/api/v1/auth/logout")
    client = logged_in(world.members[Role.OWNER])
    response = client.get("/api/v1/organization")
    assert response.status_code == 403
    assert response.json()["code"] == "no_active_organization"
