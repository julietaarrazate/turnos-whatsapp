import re
from datetime import timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.core.security import token_hash, utcnow
from app.modules.auth import create_invitation
from app.modules.auth.models import Invitation
from app.modules.identity import Membership
from tests.factories import DEFAULT_PASSWORD, create_member, create_org


def invite(org_id: UUID, email: str, role: Role = Role.QUOTER) -> str:
    with session_scope(DbContext(organization_id=org_id)) as s:
        _, message, path = create_invitation(s, org_id, email, role, invited_by_membership_id=None)
    match = re.search(r"/invite/(\S+)", message.text)
    assert match
    assert path == f"/invite/{match.group(1)}"  # el mismo token que el email
    return match.group(1)


def test_new_user_accepts_invitation(client: TestClient) -> None:
    org_id = create_org("Productora Sur")
    token = invite(org_id, "Nueva@Example.com", Role.QUOTER)

    preview = client.get(f"/api/v1/auth/invitations/{token}")
    assert preview.status_code == 200
    assert preview.json() == {
        "organization_name": "Productora Sur",
        "email": "nueva@example.com",
        "role": "QUOTER",
        "user_exists": False,
    }

    missing_name = client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": DEFAULT_PASSWORD}
    )
    assert missing_name.status_code == 422

    response = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "password": DEFAULT_PASSWORD, "name": "Nueva Persona"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["active_organization_id"] == str(org_id)
    assert body["role"] == "QUOTER"
    assert "margin.view" in body["permissions"]

    again = client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "password": DEFAULT_PASSWORD, "name": "X"},
    )
    assert again.status_code == 404


def test_existing_user_must_prove_password(client: TestClient) -> None:
    member = create_member("existe@example.com", Role.OWNER)
    second_org = create_org("Segunda")
    token = invite(second_org, "existe@example.com", Role.MANAGER)

    assert client.get(f"/api/v1/auth/invitations/{token}").json()["user_exists"] is True
    wrong = client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": "no-es-la-clave"}
    )
    assert wrong.status_code == 401

    ok = client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": DEFAULT_PASSWORD}
    )
    assert ok.status_code == 200
    orgs = {m["organization_id"] for m in ok.json()["memberships"]}
    assert orgs == {str(member.organization_id), str(second_org)}


def test_expired_or_revoked_invitations_are_invalid(client: TestClient) -> None:
    org_id = create_org()
    token = invite(org_id, "tarde@example.com")
    with session_scope(DbContext(organization_id=org_id)) as s:
        s.execute(update(Invitation).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert client.get(f"/api/v1/auth/invitations/{token}").status_code == 404

    first = invite(org_id, "dos@example.com")
    invite(org_id, "dos@example.com")  # la nueva revoca la anterior
    assert client.get(f"/api/v1/auth/invitations/{first}").status_code == 404


def test_token_only_exposes_its_own_invitation() -> None:
    org_a = create_org("A")
    org_b = create_org("B")
    token_a = invite(org_a, "a@example.com")
    invite(org_b, "b@example.com")
    with session_scope(DbContext(token_hash=token_hash(token_a))) as s:
        visible = s.execute(select(Invitation.email)).scalars().all()
    assert visible == ["a@example.com"]


def test_accepting_reactivates_disabled_membership(client: TestClient) -> None:
    member = create_member("vuelve@example.com", Role.VIEWER)
    with session_scope(DbContext(organization_id=member.organization_id)) as s:
        s.execute(update(Membership).values(status="DISABLED"))
    token = invite(member.organization_id, "vuelve@example.com", Role.MANAGER)
    response = client.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "MANAGER"
