"""Archivos del evento: subidos y links por categoría, junto con planos y fotos, y el buscador."""

from base64 import b64encode
from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in

PDF = b"%PDF-1.4 manual de marca"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


def _files(client: TestClient, world: OrgWorld) -> dict[str, Any]:
    return dict(_ok(client.get(f"/api/v1/events/{world.ids['event_id']}/files")))


def _add(client: TestClient, world: OrgWorld, **body: Any) -> Any:
    return client.post(f"/api/v1/events/{world.ids['event_id']}/files", json=body)


def test_files_link_and_upload_with_piece_and_everything_in_one_place() -> None:
    world = build_org("a")
    quoter = logged_in(world.members[Role.QUOTER])  # el brief llega por comercial
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]

    brief = _ok(
        _add(
            quoter,
            world,
            category="CLIENT",
            title="  Manual   de marca Natura ",
            file={"filename": "manual.pdf", "file_base64": b64encode(PDF).decode()},
        ),
        201,
    )
    assert (brief["source"], brief["title"], brief["mime"]) == (
        "FILE",
        "Manual de marca Natura",
        "application/pdf",
    )
    assert brief["href"] == f"/api/v1/event-files/{brief['id']}/file"
    opened = quoter.get(brief["href"])
    assert (opened.status_code, opened.content) == (200, PDF)

    render = _ok(
        _add(
            production,
            world,
            category="DESIGN",
            title="Render aprobado",
            piece_id=str(piece_id),
            url="https://drive.google.com/file/d/render",
        ),
        201,
    )
    assert (render["source"], render["piece_name"], render["href"]) == (
        "LINK",
        "Pieza ejemplo",
        "https://drive.google.com/file/d/render",
    )
    big = _ok(
        _add(production, world, category="OTHER", title="Video", url="https://we.tl/t-abc"), 201
    )
    assert big["expires_soon"] is True
    assert render["expires_soon"] is False

    # Un plano y una foto de avance aparecen solos, sin cargarlos dos veces.
    plan = {"title": "Plano de corte", "filename": "p.pdf", "file_base64": b64encode(PDF).decode()}
    _ok(production.post(f"/api/v1/pieces/{piece_id}/plans", json=plan), 201)
    photo = {"filename": "a.jpg", "file_base64": b64encode(JPEG).decode()}
    _ok(production.post(f"/api/v1/pieces/{piece_id}/updates", json={"photo": photo}), 201)

    viewer = logged_in(world.members[Role.VIEWER])
    listed = _files(viewer, world)
    by_source = {item["source"] for item in listed["items"]}
    assert by_source == {"FILE", "LINK", "PLAN", "PHOTO"}
    plan_item = next(i for i in listed["items"] if i["source"] == "PLAN")
    assert (plan_item["category"], plan_item["current"], plan_item["version"]) == (
        "DESIGN",
        True,
        1,
    )
    assert next(i for i in listed["items"] if i["source"] == "PHOTO")["category"] == "PROGRESS"
    # Solo lectura ve, pero no sube ni borra.
    assert listed["can_edit"] is False
    denied = _add(viewer, world, category="OTHER", title="X", url="https://example.com")
    assert (denied.status_code, denied.json()["code"]) == (403, "cannot_edit_files")
    assert viewer.delete(f"/api/v1/event-files/{brief['id']}").status_code == 403

    # Borrar saca el archivo de la pestaña y queda en la auditoría.
    assert production.delete(f"/api/v1/event-files/{big['id']}").status_code == 204
    assert all(i["id"] != big["id"] for i in _files(production, world)["items"])
    owner = logged_in(world.members[Role.OWNER])
    actions = [e["action"] for e in _ok(owner.get("/api/v1/audit-logs"))["items"]]
    assert "event.file_added" in actions
    assert "event.file_removed" in actions


def test_file_or_link_https_only_and_piece_of_the_same_event() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    both = _add(
        production,
        world,
        category="OTHER",
        title="X",
        url="https://a.com",
        file={"filename": "a.pdf", "file_base64": b64encode(PDF).decode()},
    )
    assert (both.status_code, both.json()["code"]) == (422, "file_or_link")
    assert _add(production, world, category="OTHER", title="X").status_code == 422
    insecure = _add(production, world, category="OTHER", title="X", url="http://a.com")
    assert (insecure.status_code, insecure.json()["code"]) == (422, "link_invalid")
    script = _add(production, world, category="OTHER", title="X", url="javascript:alert(1)")
    assert script.status_code == 422

    other = build_org("b")
    foreign = _add(
        production,
        world,
        category="DESIGN",
        title="X",
        url="https://a.com",
        piece_id=str(other.ids["piece_id"]),
    )
    assert (foreign.status_code, foreign.json()["code"]) == (422, "piece_not_in_event")


def test_deleting_a_piece_keeps_its_files_in_the_event() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    piece_id = world.ids["piece_id"]
    item = _ok(
        _add(
            owner,
            world,
            category="DESIGN",
            title="Render",
            url="https://a.com/r",
            piece_id=str(piece_id),
        ),
        201,
    )
    assert owner.delete(f"/api/v1/pieces/{piece_id}").status_code == 204
    kept = next(i for i in _files(owner, world)["items"] if i["id"] == item["id"])
    assert (kept["piece_id"], kept["piece_name"]) == (None, None)


def test_search_across_events_and_closed_events_are_read_only() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    _ok(
        _add(
            owner, world, category="CLIENT", title="Logo Natura vectorial", url="https://a.com/logo"
        ),
        201,
    )

    found = _ok(owner.get("/api/v1/files/search", params={"q": "logo natura"}))
    assert any(i["title"] == "Logo Natura vectorial" for i in found)
    assert found[0]["event"]["name"] == "Evento ejemplo"
    # Por nombre del evento también; y lo de otra organización no aparece.
    assert _ok(owner.get("/api/v1/files/search", params={"q": "ejemplo"}))
    other = logged_in(build_org("b").members[Role.OWNER])
    assert _ok(other.get("/api/v1/files/search", params={"q": "logo natura"})) == []
    assert _ok(owner.get("/api/v1/files/search", params={"q": "%"})) == []

    _approved(world)
    base = f"/api/v1/events/{world.ids['event_id']}"
    _ok(owner.post(f"{base}/start-production"))
    _ok(owner.post(f"{base}/complete"))
    _ok(owner.post(f"{base}/close"))
    locked = _add(owner, world, category="OTHER", title="Tarde", url="https://a.com")
    assert (locked.status_code, locked.json()["code"]) == (409, "event_locked")
    assert _files(owner, world)["items"]  # se sigue viendo
