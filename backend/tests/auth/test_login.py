from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.config import Settings
from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.main import create_app
from app.modules.organizations import Membership
from app.modules.users import User
from tests.factories import DEFAULT_PASSWORD, add_member, create_member, create_org


def login(client: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> dict[str, object]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_login_returns_profile_and_sets_secure_cookies(client: TestClient) -> None:
    member = create_member("owner@example.com", Role.OWNER)
    response = client.post(
        "/api/v1/auth/login", json={"email": "OWNER@example.com", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "owner@example.com"
    assert body["active_organization_id"] == str(member.organization_id)
    assert body["role"] == "OWNER"
    assert "org.fiscal.manage" in body["permissions"]

    cookies = response.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("access_token="))
    refresh = next(c for c in cookies if c.startswith("refresh_token="))
    for cookie in (access, refresh):
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
    assert "Path=/api/v1/auth" in refresh


def test_wrong_password_and_unknown_email_look_the_same(client: TestClient) -> None:
    create_member("owner@example.com")
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "otra-cosa-123"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nadie@example.com", "password": "otra-cosa-123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "invalid_credentials"
    assert wrong.headers["content-type"] == "application/problem+json"


def test_inactive_user_cannot_login(client: TestClient) -> None:
    member = create_member("owner@example.com")
    with session_scope() as s:
        s.execute(update(User).where(User.id == member.user_id).values(is_active=False))
    response = client.post(
        "/api/v1/auth/login", json={"email": member.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 401


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_cookie_and_with_bearer(client: TestClient) -> None:
    create_member("owner@example.com")
    login(client, "owner@example.com")
    assert client.get("/api/v1/auth/me").status_code == 200

    token = client.cookies.get("access_token")
    bare = TestClient(client.app)
    response = bare.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_tampered_token_is_rejected(client: TestClient) -> None:
    create_member("owner@example.com")
    login(client, "owner@example.com")
    token = str(client.cookies.get("access_token"))
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    bare = TestClient(client.app)
    response = bare.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


def test_csrf_header_is_required_for_mutations() -> None:
    create_member("owner@example.com")
    bare = TestClient(create_app())
    response = bare.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_header"


def test_foreign_origin_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "x@example.com", "password": DEFAULT_PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_origin"


def test_login_is_rate_limited_per_email(client: TestClient) -> None:
    create_member("owner@example.com")
    for _ in range(10):
        client.post(
            "/api/v1/auth/login", json={"email": "owner@example.com", "password": "mal-mal-mal"}
        )
    response = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 429


def test_rate_limit_can_be_disabled(client: TestClient, settings: Settings) -> None:
    settings.rate_limit_enabled = False
    create_member("owner@example.com")
    for _ in range(12):
        client.post(
            "/api/v1/auth/login", json={"email": "owner@example.com", "password": "mal-mal-mal"}
        )
    assert login(client, "owner@example.com")


def test_disabled_membership_loses_access_immediately(client: TestClient) -> None:
    member = create_member("owner@example.com")
    login(client, "owner@example.com")
    with session_scope(DbContext(organization_id=member.organization_id)) as s:
        s.execute(
            update(Membership)
            .where(Membership.id == member.membership_id)
            .values(status="DISABLED")
        )
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 403
    assert response.json()["code"] == "membership_inactive"


def test_user_without_organizations_logs_in_without_active_org(client: TestClient) -> None:
    member = create_member("owner@example.com")
    with session_scope(DbContext(organization_id=member.organization_id)) as s:
        s.execute(update(Membership).values(status="DISABLED"))
    body = login(client, "owner@example.com")
    assert body["active_organization_id"] is None
    assert body["permissions"] == []


def test_switch_organization(client: TestClient) -> None:
    member = create_member("multi@example.com", Role.OWNER)
    other_org = create_org("Otra productora")
    add_member(other_org, member.user_id, member.email, Role.VIEWER)
    stranger_org = create_org("Ajena")

    body = login(client, "multi@example.com")
    assert len(body["memberships"]) == 2  # type: ignore[arg-type]

    response = client.post(
        "/api/v1/auth/switch-organization", json={"organization_id": str(other_org)}
    )
    assert response.status_code == 200
    assert response.json()["active_organization_id"] == str(other_org)
    assert response.json()["role"] == "VIEWER"
    assert client.get("/api/v1/auth/me").json()["role"] == "VIEWER"

    response = client.post(
        "/api/v1/auth/switch-organization", json={"organization_id": str(stranger_org)}
    )
    assert response.status_code == 404
