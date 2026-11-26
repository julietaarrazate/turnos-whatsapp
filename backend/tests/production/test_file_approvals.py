"""Aprobación de diseños por link: el cliente aprueba o pide cambios sin cuenta; queda registro."""

from base64 import b64encode
from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from app.main import create_app
from tests.production.test_event_files import JPEG, _add, _files
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in


def _public() -> TestClient:
    return TestClient(create_app(), headers={"X-Requested-With": "fetch"})


def _token(path: str) -> str:
    assert path.startswith("/a/")
    return path.removeprefix("/a/")


def _render(client: TestClient, world: OrgWorld) -> dict[str, Any]:
    return dict(
        _ok(
            _add(
                client,
                world,
                category="DESIGN",
                title="Render stand Natura",
                file={"filename": "render.jpg", "file_base64": b64encode(JPEG).decode()},
            ),
            201,
        )
    )


def _ask(client: TestClient, file_id: str) -> dict[str, Any]:
    return dict(_ok(client.post(f"/api/v1/event-files/{file_id}/approval"), 201))


def test_client_approves_from_the_link_and_the_team_sees_who_and_when() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    render = _render(production, world)
    link = _ask(production, render["id"])
    assert link["approval"]["status"] == "PENDING"
    token = _token(link["path"])

    client = _public()
    seen = _ok(client.get(f"/api/v1/public/approvals/{token}"))
    assert (seen["title"], seen["kind"], seen["status"]) == (
        "Render stand Natura",
        "IMAGE",
        "PENDING",
    )
    assert seen["event_name"]
    assert seen["organization_name"]
    assert "total" not in str(seen).lower()  # lista blanca: nada de plata
    image = client.get(f"/api/v1/public/approvals/{token}/file")
    assert (image.status_code, image.content) == (200, JPEG)

    done = _ok(
        client.post(
            f"/api/v1/public/approvals/{token}/decision",
            json={"decision": "APPROVED", "name": "  Laura (Natura) "},
        )
    )
    assert (done["status"], done["decided_by_name"]) == ("APPROVED", "Laura (Natura)")
    # No se responde dos veces.
    again = client.post(
        f"/api/v1/public/approvals/{token}/decision", json={"decision": "CHANGES", "name": "Otro"}
    )
    assert (again.status_code, again.json()["code"]) == (409, "approval_decided")

    item = next(i for i in _files(production, world)["items"] if i["id"] == render["id"])
    assert item["approval"]["status"] == "APPROVED"
    assert item["approval"]["decided_by_name"] == "Laura (Natura)"

    viewer = logged_in(world.members[Role.VIEWER])
    news = _ok(viewer.get("/api/v1/activity"))["items"][0]
    assert (news["kind"], news["actor_name"], news["status"], news["title"]) == (
        "file.approval_decided",
        "Laura (Natura)",
        "APPROVED",
        "Render stand Natura",
    )


def test_changes_need_a_comment_and_a_new_round_replaces_the_old_link() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    link_file = world.ids["file_id"]  # un link de Drive del harness
    first = _token(_ask(owner, str(link_file))["path"])
    client = _public()
    assert _ok(client.get(f"/api/v1/public/approvals/{first}"))["kind"] == "LINK"
    assert client.get(f"/api/v1/public/approvals/{first}/file").status_code == 404

    empty = client.post(
        f"/api/v1/public/approvals/{first}/decision", json={"decision": "CHANGES", "name": "Laura"}
    )
    assert (empty.status_code, empty.json()["code"]) == (422, "comment_required")
    changes = _ok(
        client.post(
            f"/api/v1/public/approvals/{first}/decision",
            json={"decision": "CHANGES", "name": "Laura", "comment": "Logo más grande"},
        )
    )
    assert (changes["status"], changes["comment"]) == ("CHANGES", "Logo más grande")

    # Segunda vuelta: link nuevo; un pedido sin responder se anula al pedir otro.
    second = _ask(owner, str(link_file))
    assert second["approval"]["rounds"] == 2
    third = _ask(owner, str(link_file))
    stale = client.post(
        f"/api/v1/public/approvals/{_token(second['path'])}/decision",
        json={"decision": "APPROVED", "name": "Laura"},
    )
    assert (stale.status_code, stale.json()["code"]) == (410, "approval_replaced")
    assert third["approval"]["rounds"] == 2
    assert (
        _ok(client.get(f"/api/v1/public/approvals/{_token(third['path'])}"))["status"] == "PENDING"
    )


def test_only_who_edits_files_asks_and_bad_or_foreign_tokens_get_nothing() -> None:
    world = build_org("a")
    viewer = logged_in(world.members[Role.VIEWER])
    denied = viewer.post(f"/api/v1/event-files/{world.ids['file_id']}/approval")
    assert (denied.status_code, denied.json()["code"]) == (403, "files_read_only")

    other = build_org("b")
    stranger = logged_in(other.members[Role.OWNER])
    assert stranger.post(f"/api/v1/event-files/{world.ids['file_id']}/approval").status_code == 404

    client = _public()
    assert client.get("/api/v1/public/approvals/" + "x" * 43).status_code == 404


def test_closed_event_takes_no_new_requests() -> None:
    world = build_org("a")
    _approved(world)
    manager = logged_in(world.members[Role.MANAGER])
    base = f"/api/v1/events/{world.ids['event_id']}"
    _ok(manager.post(f"{base}/start-production"))
    _ok(manager.post(f"{base}/complete"))
    _ok(manager.post(f"{base}/close"))
    blocked = manager.post(f"/api/v1/event-files/{world.ids['file_id']}/approval")
    assert (blocked.status_code, blocked.json()["code"]) == (409, "event_locked")
