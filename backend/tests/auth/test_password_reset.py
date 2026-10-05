import re
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.db import session_scope
from app.core.security import utcnow
from app.modules.auth.models import PasswordResetToken
from app.modules.notifications import console_backend
from tests.auth.test_login import login
from tests.factories import DEFAULT_PASSWORD, create_member

NEW_PASSWORD = "otra-contraseña-456"


def _request_token(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/password-reset", json={"email": email})
    assert response.status_code == 202
    [message] = console_backend.sent
    match = re.search(r"/reset-password/(\S+)", message.text)
    assert match
    return match.group(1)


def test_unknown_email_gets_same_answer_and_no_email(client: TestClient) -> None:
    response = client.post("/api/v1/auth/password-reset", json={"email": "nadie@example.com"})
    assert response.status_code == 202
    assert console_backend.sent == []


def test_reset_changes_password_and_closes_sessions(client: TestClient) -> None:
    create_member("owner@example.com")
    login(client, "owner@example.com")
    old_session = TestClient(client.app, headers={"X-Requested-With": "fetch"})
    old_session.cookies = client.cookies

    token = _request_token(client, "owner@example.com")
    response = client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 204
    assert old_session.get("/api/v1/auth/me").status_code == 401

    bad = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": DEFAULT_PASSWORD}
    )
    assert bad.status_code == 401
    assert login(client, "owner@example.com", NEW_PASSWORD)

    reused = client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
    )
    assert reused.status_code == 400


def test_expired_reset_token_is_rejected(client: TestClient) -> None:
    create_member("owner@example.com")
    token = _request_token(client, "owner@example.com")
    with session_scope() as s:
        s.execute(update(PasswordResetToken).values(expires_at=utcnow() - timedelta(seconds=1)))
    response = client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "reset_token_invalid"


def test_short_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": "x", "password": "corta"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
