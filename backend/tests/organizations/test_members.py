from app.core.enums import Role
from app.modules.notifications import console_backend
from tests.security.harness import build_org, logged_in


def test_email_is_redacted_for_roles_that_cannot_manage_members() -> None:
    world = build_org("a")
    as_viewer = logged_in(world.members[Role.VIEWER]).get("/api/v1/members").json()
    as_admin = logged_in(world.members[Role.ADMIN]).get("/api/v1/members").json()
    assert all(m["email"] is None for m in as_viewer)
    assert all(m["email"] for m in as_admin)


def test_admin_cannot_create_or_touch_owners() -> None:
    world = build_org("a")
    admin = logged_in(world.members[Role.ADMIN])
    promote = admin.patch(f"/api/v1/members/{world.target.membership_id}", json={"role": "OWNER"})
    assert promote.status_code == 403
    assert promote.json()["code"] == "owner_required"
    owner_id = world.members[Role.OWNER].membership_id
    demote = admin.patch(f"/api/v1/members/{owner_id}", json={"role": "VIEWER"})
    assert demote.status_code == 403
    invite_owner = admin.post("/api/v1/invitations", json={"email": "x@e.com", "role": "OWNER"})
    assert invite_owner.status_code == 403


def test_the_last_owner_cannot_be_demoted() -> None:
    world = build_org("a")
    owner = world.members[Role.OWNER]
    client = logged_in(owner)
    response = client.patch(f"/api/v1/members/{owner.membership_id}", json={"role": "ADMIN"})
    assert response.status_code == 409
    assert response.json()["code"] == "last_owner"
    # Con un segundo OWNER, sí.
    promote = client.patch(f"/api/v1/members/{world.target.membership_id}", json={"role": "OWNER"})
    assert promote.status_code == 200
    response = client.patch(f"/api/v1/members/{owner.membership_id}", json={"role": "ADMIN"})
    assert response.status_code == 200


def test_cannot_disable_yourself() -> None:
    world = build_org("a")
    admin = world.members[Role.ADMIN]
    response = logged_in(admin).patch(
        f"/api/v1/members/{admin.membership_id}", json={"status": "DISABLED"}
    )
    assert response.status_code == 409


def test_disabling_a_member_cuts_access_and_is_audited() -> None:
    world = build_org("a")
    target_client = logged_in(world.target)
    owner = logged_in(world.members[Role.OWNER])
    response = owner.patch(
        f"/api/v1/members/{world.target.membership_id}", json={"status": "DISABLED"}
    )
    assert response.status_code == 200
    assert target_client.get("/api/v1/members").status_code == 403

    [entry] = [
        e
        for e in owner.get("/api/v1/audit-logs").json()["items"]
        if e["action"] == "membership.disabled"
    ]
    assert entry["entity_id"] == str(world.target.membership_id)
    assert entry["before"] == {"status": "ACTIVE"}
    assert entry["after"] == {"status": "DISABLED"}
    assert entry["actor_user_id"] == str(world.members[Role.OWNER].user_id)


def test_invitation_lifecycle() -> None:
    world = build_org("a")
    admin = logged_in(world.members[Role.ADMIN])
    created = admin.post(
        "/api/v1/invitations", json={"email": "Nueva@Example.com", "role": "QUOTER"}
    )
    assert created.status_code == 201
    assert created.json()["email"] == "nueva@example.com"
    assert [m.to for m in console_backend.sent] == ["nueva@example.com"]
    # El link se devuelve una sola vez (sin email configurado, se comparte por WhatsApp) y es
    # el mismo del email: sirve para aceptar la invitación.
    path = created.json()["invite_path"]
    assert created.json()["emailed"] is False  # EMAIL_BACKEND=console
    assert path in console_backend.sent[0].text
    preview = admin.get(f"/api/v1/auth/invitations/{path.removeprefix('/invite/')}")
    assert (preview.status_code, preview.json()["email"]) == (200, "nueva@example.com")

    listed = admin.get("/api/v1/invitations").json()
    assert "nueva@example.com" in {i["email"] for i in listed}
    assert all("invite_path" not in i for i in listed)  # la lista nunca lo muestra

    invitation_id = created.json()["id"]
    assert admin.delete(f"/api/v1/invitations/{invitation_id}").status_code == 204
    assert admin.delete(f"/api/v1/invitations/{invitation_id}").status_code == 404


def test_cannot_invite_an_active_member() -> None:
    world = build_org("a")
    admin = logged_in(world.members[Role.ADMIN])
    response = admin.post(
        "/api/v1/invitations", json={"email": world.target.email, "role": "QUOTER"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "already_member"
