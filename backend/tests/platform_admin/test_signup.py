"""Crear cuenta: la productora queda esperando aprobación de la dueña de la plataforma."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.modules.notifications import console_backend
from app.modules.platform.signup import MAX_PENDING_SIGNUPS
from tests.auth.test_login import login
from tests.conftest import make_client
from tests.factories import DEFAULT_PASSWORD, create_member, create_user

ADMIN = "duena@plataforma.example.com"


def _signup(client: TestClient, email: str = "nueva@productora.example.com", **extra: str):
    body = {
        "name": "  Ana   Pérez ",
        "organization_name": "Productora Nueva",
        "email": email,
        "password": DEFAULT_PASSWORD,
        **extra,
    }
    return client.post("/api/v1/auth/signup", json=body)


@pytest.fixture
def admin(settings: Settings) -> TestClient:
    settings.platform_admins = ADMIN
    create_user(ADMIN, name="Dueña")
    client = make_client()
    login(client, ADMIN)
    return client


def test_signup_waits_for_approval_and_the_admin_approves(admin: TestClient) -> None:
    console_backend.sent.clear()
    client = make_client()
    created = _signup(client)
    assert created.status_code == 200, created.text
    me = created.json()
    assert me["user"]["name"] == "Ana Pérez"
    assert me["active_organization_id"] is None
    assert me["pending_organization"] == "Productora Nueva"
    denied = client.get("/api/v1/clients")
    assert (denied.status_code, denied.json()["code"]) == (403, "no_active_organization")
    assert [e.to for e in console_backend.sent] == [ADMIN]

    org = next(o for o in admin.get("/api/v1/admin/overview").json()["organizations"])
    assert org["pending_approval"] is True
    assert admin.post(f"/api/v1/admin/organizations/{org['id']}/approve").status_code == 204
    assert console_backend.sent[-1].to == "nueva@productora.example.com"

    # Al volver a entrar ya trabaja con su productora, con el catálogo base cargado.
    again = make_client()
    me = login(again, "nueva@productora.example.com")
    assert me["active_organization_id"] == org["id"]
    assert me["pending_organization"] is None
    assert me["role"] == "OWNER"
    assert again.get("/api/v1/catalog/categories").json()


def test_signup_rejects_taken_emails_robots_and_floods(settings: Settings) -> None:
    create_member("ya@existe.example.com")
    taken = _signup(make_client(), "YA@existe.example.com")
    assert (taken.status_code, taken.json()["code"]) == (409, "email_taken")

    robot = _signup(make_client(), "robot@example.com", website="http://spam.example.com")
    assert robot.status_code == 422

    settings.rate_limit_enabled = False
    for i in range(MAX_PENDING_SIGNUPS):
        assert _signup(make_client(), f"p{i}@example.com").status_code == 200
    flood = _signup(make_client(), "una-mas@example.com")
    assert (flood.status_code, flood.json()["code"]) == (429, "signups_paused")


def test_signup_is_rate_limited_by_ip(settings: Settings) -> None:
    settings.rate_limit_enabled = True
    client = make_client()
    codes = [_signup(client, f"r{i}@example.com").status_code for i in range(6)]
    assert codes == [200] * 5 + [429]


def test_rejecting_a_signup_pauses_it(admin: TestClient) -> None:
    client = make_client()
    _signup(client)
    org = admin.get("/api/v1/admin/overview").json()["organizations"][0]
    assert admin.post(f"/api/v1/admin/organizations/{org['id']}/suspend").status_code == 204
    me = client.get("/api/v1/auth/me").json()
    assert me["pending_organization"] is None
    assert me["active_organization_id"] is None


def test_once_approved_the_open_session_moves_in_on_its_next_refresh(admin: TestClient) -> None:
    client = make_client()
    _signup(client)
    org = admin.get("/api/v1/admin/overview").json()["organizations"][0]
    admin.post(f"/api/v1/admin/organizations/{org['id']}/approve")

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.json()["active_organization_id"] == org["id"]
    assert client.get("/api/v1/clients").status_code == 200
