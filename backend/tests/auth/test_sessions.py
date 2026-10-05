from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.auth.test_login import login
from tests.factories import create_member


def test_refresh_rotates_the_token(client: TestClient) -> None:
    create_member("owner@example.com")
    login(client, "owner@example.com")
    first = client.cookies.get("refresh_token")
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert client.cookies.get("refresh_token") != first


def test_reusing_a_rotated_token_revokes_the_session(
    client: TestClient, settings: Settings
) -> None:
    settings.refresh_reuse_grace_seconds = 0
    create_member("owner@example.com")
    login(client, "owner@example.com")
    stolen = str(client.cookies.get("refresh_token"))
    assert client.post("/api/v1/auth/refresh").status_code == 200
    legit = str(client.cookies.get("refresh_token"))

    attacker = TestClient(client.app, headers={"X-Requested-With": "fetch"})
    attacker.cookies.set("refresh_token", stolen, path="/api/v1/auth")
    response = attacker.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["code"] == "session_revoked"

    # La revocación alcanza también al usuario legítimo (toda la familia de tokens).
    client.cookies.set("refresh_token", legit, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_reuse_within_grace_window_is_tolerated(client: TestClient) -> None:
    create_member("owner@example.com")
    login(client, "owner@example.com")
    token = str(client.cookies.get("refresh_token"))
    assert client.post("/api/v1/auth/refresh").status_code == 200

    other_tab = TestClient(client.app, headers={"X-Requested-With": "fetch"})
    other_tab.cookies.set("refresh_token", token, path="/api/v1/auth")
    assert other_tab.post("/api/v1/auth/refresh").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200


def test_refresh_without_cookie_is_unauthorized(client: TestClient) -> None:
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revokes_access_and_refresh(client: TestClient) -> None:
    create_member("owner@example.com")
    login(client, "owner@example.com")
    access = str(client.cookies.get("access_token"))
    refresh = str(client.cookies.get("refresh_token"))
    assert client.post("/api/v1/auth/logout").status_code == 204

    other = TestClient(client.app, headers={"X-Requested-With": "fetch"})
    assert (
        other.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code
        == 401
    )
    other.cookies.set("refresh_token", refresh, path="/api/v1/auth")
    assert other.post("/api/v1/auth/refresh").status_code == 401


def test_logout_without_session_is_idempotent(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204
