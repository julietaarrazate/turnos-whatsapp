from fastapi.testclient import TestClient

from app.core.observability import _scrub, redact_tokens
from app.main import create_app


def test_healthz() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_checks_the_database() -> None:
    assert TestClient(create_app()).get("/readyz").json() == {"status": "ok"}


def test_request_id_is_generated_or_propagated() -> None:
    client = TestClient(create_app())
    generated = client.get("/healthz").headers["X-Request-Id"]
    assert len(generated) == 32
    propagated = client.get("/healthz", headers={"X-Request-Id": "abc12345-from-next"})
    assert propagated.headers["X-Request-Id"] == "abc12345-from-next"
    # Un id inválido (inyección en logs) se reemplaza.
    bad = client.get("/healthz", headers={"X-Request-Id": "x\nfake-log-line"})
    assert bad.headers["X-Request-Id"] != "x\nfake-log-line"


def test_sentry_scrubbing_removes_secrets_and_bodies() -> None:
    event = {
        "transaction": "/api/v1/auth/invitations/secreto123",
        "request": {
            "url": "https://api.x/api/v1/auth/invitations/secreto123",
            "data": {"password": "secreta"},
            "cookies": {"refresh_token": "t"},
            "headers": {"Authorization": "Bearer x", "Cookie": "a=b", "Accept": "json"},
        },
    }
    scrubbed = _scrub(event, None)
    assert "data" not in scrubbed["request"]
    assert "cookies" not in scrubbed["request"]
    assert scrubbed["request"]["headers"]["Authorization"] == "[filtrado]"
    assert scrubbed["request"]["headers"]["Cookie"] == "[filtrado]"
    assert scrubbed["request"]["headers"]["Accept"] == "json"
    assert "secreto123" not in scrubbed["request"]["url"]
    assert scrubbed["transaction"] == "/api/v1/auth/invitations/[token]"
    assert redact_tokens("/api/v1/auth/invitations/accept") == "/api/v1/auth/invitations/accept"
