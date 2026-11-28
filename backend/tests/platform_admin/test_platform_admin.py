"""Panel de la dueña de la plataforma: ve todas las organizaciones y puede pausar accesos.
Para cualquier otra persona el panel no existe (404, igual que una ruta inexistente)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings
from app.core.db import DbContext, session_scope
from tests.auth.test_login import login
from tests.conftest import make_client
from tests.factories import create_member, create_user

ADMIN = "duena@plataforma.example.com"


@pytest.fixture
def admin(settings: Settings) -> TestClient:
    settings.platform_admins = f"otra@example.com, {ADMIN.upper()}"
    create_user(ADMIN, name="Dueña")  # sin organización propia: igual ve el panel
    client = make_client()
    login(client, ADMIN)
    return client


def test_only_the_platform_admin_sees_the_panel(admin: TestClient) -> None:
    owner = create_member("owner@productora.example.com")
    other = make_client()
    login(other, owner.email)

    unknown = other.get("/api/v1/admin/no-existe")
    for method, path in [
        ("GET", "/api/v1/admin/overview"),
        ("POST", f"/api/v1/admin/users/{owner.user_id}/suspend"),
        ("POST", f"/api/v1/admin/organizations/{owner.organization_id}/suspend"),
        ("POST", "/api/v1/admin/sessions/no-es-un-id/close"),
    ]:
        for client in (other, make_client()):  # con sesión de otra persona y sin sesión
            response = client.request(method, path)
            assert response.status_code == 404, (method, path)
            assert response.json() == unknown.json()
    assert other.get("/api/v1/auth/me").json()["platform_admin"] is False
    assert admin.get("/api/v1/auth/me").json()["platform_admin"] is True


def test_overview_lists_every_organization_user_session_and_activity(admin: TestClient) -> None:
    a = create_member("owner@a.example.com")
    b = create_member("owner@b.example.com")
    for member in (a, b):
        client = make_client()
        login(client, member.email)
        assert client.patch("/api/v1/organization", json={"follow_up_days": 7}).status_code == 200

    data = admin.get("/api/v1/admin/overview").json()
    orgs = {o["id"]: o for o in data["organizations"]}
    assert set(orgs) == {str(a.organization_id), str(b.organization_id)}
    assert [m["email"] for m in orgs[str(a.organization_id)]["members"]] == [a.email]
    assert orgs[str(a.organization_id)]["last_activity_at"] is not None

    users = {u["email"]: u for u in data["users"]}
    assert users[ADMIN]["is_me"] is True
    assert users[ADMIN]["organizations"] == []
    assert users[a.email]["open_sessions"] == 1
    assert users[a.email]["last_login_at"] is not None
    assert len([s for s in data["sessions"] if s["is_current"]]) == 1
    actions = [(x["organization_name"], x["action"]) for x in data["activity"]]
    assert actions.count(("Productora", "org.settings_changed")) == 2


def test_the_platform_flag_only_opens_the_organization_list() -> None:
    """La política nueva deja leer nombres de organizaciones; nada de adentro de ellas."""
    create_member("owner@a.example.com")
    with session_scope(DbContext(platform_admin=True)) as s:
        assert s.execute(text("SELECT count(*) FROM organizations")).scalar() == 1
        assert s.execute(text("SELECT count(*) FROM memberships")).scalar() == 0
        assert s.execute(text("SELECT count(*) FROM audit_logs")).scalar() == 0
        assert s.execute(text("SELECT count(*) FROM clients")).scalar() == 0
    with session_scope() as s:
        assert s.execute(text("SELECT count(*) FROM organizations")).scalar() == 0


def test_suspending_a_user_closes_their_sessions_and_blocks_login(admin: TestClient) -> None:
    owner = create_member("owner@productora.example.com")
    phone = make_client()
    login(phone, owner.email)

    assert admin.post(f"/api/v1/admin/users/{owner.user_id}/suspend").status_code == 204
    assert phone.get("/api/v1/auth/me").status_code == 401
    blocked = make_client().post(
        "/api/v1/auth/login", json={"email": owner.email, "password": owner.password}
    )
    assert blocked.status_code == 401

    assert admin.post(f"/api/v1/admin/users/{owner.user_id}/reactivate").status_code == 204
    login(make_client(), owner.email)

    me = admin.get("/api/v1/auth/me").json()["user"]["id"]
    myself = admin.post(f"/api/v1/admin/users/{me}/suspend")
    assert (myself.status_code, myself.json()["code"]) == (409, "cannot_suspend_self")


def test_pausing_an_organization_cuts_access_until_reactivated(admin: TestClient) -> None:
    owner = create_member("owner@productora.example.com")
    phone = make_client()
    login(phone, owner.email)
    assert phone.get("/api/v1/clients").status_code == 200

    org = owner.organization_id
    assert admin.post(f"/api/v1/admin/organizations/{org}/suspend").status_code == 204
    me = phone.get("/api/v1/auth/me").json()
    assert me["active_organization_id"] is None
    assert me["memberships"] == []
    denied = phone.get("/api/v1/clients")
    assert (denied.status_code, denied.json()["code"]) == (403, "no_active_organization")
    again = make_client()
    login(again, owner.email)
    assert again.get("/api/v1/auth/me").json()["active_organization_id"] is None
    overview = admin.get("/api/v1/admin/overview").json()
    assert overview["organizations"][0]["suspended_at"] is not None

    assert admin.post(f"/api/v1/admin/organizations/{org}/reactivate").status_code == 204
    assert phone.get("/api/v1/clients").status_code == 200


def test_closing_a_session_logs_that_device_out(admin: TestClient) -> None:
    owner = create_member("owner@productora.example.com")
    phone = make_client()
    login(phone, owner.email)
    sessions = admin.get("/api/v1/admin/overview").json()["sessions"]
    target = next(s for s in sessions if s["user_name"] != "Dueña")
    mine = next(s for s in sessions if s["is_current"])

    assert admin.post(f"/api/v1/admin/sessions/{target['id']}/close").status_code == 204
    assert phone.get("/api/v1/auth/me").status_code == 401
    own = admin.post(f"/api/v1/admin/sessions/{mine['id']}/close")
    assert (own.status_code, own.json()["code"]) == (409, "cannot_close_own_session")
