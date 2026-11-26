"""Avances de una pieza: foto y/o nota, quién los sube y quién los ve, y el tope de espacio."""

from base64 import b64encode
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.enums import Role
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200  # alcanza la firma: el servidor mira el contenido
PDF = b"%PDF-1.4 " + b"0" * 200


def _photo(data: bytes = JPEG, name: str = "avance.jpg") -> dict[str, str]:
    return {"filename": name, "file_base64": b64encode(data).decode()}


def _post(client: TestClient, piece_id: Any, **body: Any) -> Any:
    return client.post(f"/api/v1/pieces/{piece_id}/updates", json=body)


def _assign(world: OrgWorld, role: Role) -> str:
    owner = logged_in(world.members[Role.OWNER])
    piece_id = world.ids["piece_id"]
    member = str(world.members[role].user_id)
    _ok(owner.patch(f"/api/v1/pieces/{piece_id}", json={"assignee_user_id": member}))
    return str(piece_id)


def test_production_posts_photo_and_note_and_everyone_who_sees_the_event_sees_it() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]

    created = _ok(_post(production, piece_id, note="  Letras cortadas ", photo=_photo()), 201)
    assert created["note"] == "Letras cortadas"
    assert created["has_photo"] is True
    assert created["author_name"]

    # Lo más nuevo primero (el harness ya trae un avance de ejemplo, solo nota).
    quoter = logged_in(world.members[Role.QUOTER])
    listed = _ok(quoter.get(f"/api/v1/pieces/{piece_id}/updates"))
    assert [u["note"] for u in listed][:2] == ["Letras cortadas", "Avance ejemplo"]

    photo = quoter.get(f"/api/v1/piece-updates/{created['id']}/photo")
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/jpeg"
    assert photo.headers["x-content-type-options"] == "nosniff"
    assert photo.content == JPEG

    # Comercial ve, pero no sube avances (no es de producción ni tiene la pieza).
    denied = _post(quoter, piece_id, note="Hola")
    assert (denied.status_code, denied.json()["code"]) == (403, "not_assigned")

    owner = logged_in(world.members[Role.OWNER])
    actions = [e["action"] for e in _ok(owner.get("/api/v1/audit-logs"))["items"]]
    assert "piece.update_posted" in actions


def test_crew_posts_only_on_their_own_piece() -> None:
    world = build_org("a")
    crew = logged_in(world.members[Role.CREW])
    piece_id = world.ids["piece_id"]

    # Sin asignar: para el taller la pieza no existe.
    assert _post(crew, piece_id, note="Listo").status_code == 404
    assert crew.get(f"/api/v1/pieces/{piece_id}/updates").status_code == 404

    _assign(world, Role.CREW)
    created = _ok(_post(crew, piece_id, photo=_photo()), 201)
    assert created["note"] is None
    assert len(_ok(crew.get(f"/api/v1/pieces/{piece_id}/updates"))) == 2
    assert crew.get(f"/api/v1/piece-updates/{created['id']}/photo").status_code == 200


def test_only_photos_and_something_to_say() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]

    empty = _post(production, piece_id, note="   ")
    assert (empty.status_code, empty.json()["code"]) == (422, "update_empty")
    pdf = _post(production, piece_id, photo=_photo(PDF, "plano.pdf"))
    assert (pdf.status_code, pdf.json()["code"]) == (415, "upload_unsupported")
    fake = _post(production, piece_id, photo=_photo(b"<html>hola</html>", "x.jpg"))
    assert fake.status_code == 415


def test_storage_cap_blocks_uploads_and_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]
    _ok(_post(production, piece_id, photo=_photo()), 201)

    usage = _ok(production.get("/api/v1/documents/storage"))
    assert usage["used"] >= len(JPEG)
    assert usage["limit"] == get_settings().storage_quota_bytes
    assert usage["enabled"] is True

    monkeypatch.setattr(get_settings(), "storage_quota_bytes", usage["used"] + 10)
    full = _post(production, piece_id, photo=_photo())
    assert (full.status_code, full.json()["code"]) == (409, "storage_full")
    # Una nota sola no ocupa espacio de archivos: se puede seguir avisando.
    assert _post(production, piece_id, note="Sin lugar para fotos").status_code == 201


def test_closed_event_takes_no_more_updates() -> None:
    world = build_org("a")
    _approved(world)
    manager = logged_in(world.members[Role.MANAGER])
    base = f"/api/v1/events/{world.ids['event_id']}"
    _ok(manager.post(f"{base}/start-production"))
    _ok(manager.post(f"{base}/complete"))
    _ok(manager.post(f"{base}/close"))
    blocked = _post(manager, world.ids["piece_id"], note="Tarde")
    assert (blocked.status_code, blocked.json()["code"]) == (409, "event_locked")
    assert len(_ok(manager.get(f"/api/v1/pieces/{world.ids['piece_id']}/updates"))) == 1


WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 300  # firma EBML/WebM, como graba Chrome
OGG = b"OggS" + b"\x00" * 300
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 300  # como graba el iPhone


def _audio(data: bytes = WEBM, name: str = "nota.webm") -> dict[str, str]:
    return {"filename": name, "file_base64": b64encode(data).decode()}


def test_voice_note_alone_or_with_photo_and_it_plays_back() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]

    voice = _ok(_post(production, piece_id, audio=_audio()), 201)
    assert (voice["has_audio"], voice["has_photo"], voice["note"]) == (True, False, None)
    played = production.get(f"/api/v1/piece-updates/{voice['id']}/audio")
    assert played.status_code == 200
    assert played.headers["content-type"] == "audio/webm"
    assert played.headers["x-content-type-options"] == "nosniff"
    assert played.content == WEBM

    both = _ok(_post(production, piece_id, photo=_photo(), audio=_audio(M4A, "nota.m4a")), 201)
    assert (both["has_photo"], both["has_audio"]) == (True, True)
    ogg = _ok(_post(production, piece_id, audio=_audio(OGG, "nota.ogg")), 201)
    assert (
        production.get(f"/api/v1/piece-updates/{ogg['id']}/audio").headers["content-type"]
        == "audio/ogg"
    )

    # Un avance sin audio no tiene qué reproducir; el de otra persona ajena, tampoco.
    note_only = _ok(_post(production, piece_id, note="Sin audio"), 201)
    assert production.get(f"/api/v1/piece-updates/{note_only['id']}/audio").status_code == 404
    crew = logged_in(world.members[Role.CREW])
    assert crew.get(f"/api/v1/piece-updates/{voice['id']}/audio").status_code == 404

    viewer = logged_in(world.members[Role.VIEWER])
    item = _ok(viewer.get("/api/v1/activity"))["items"][3]
    assert (item["kind"], item["has_audio"], item["update_id"]) == (
        "piece.update_posted",
        True,
        voice["id"],
    )


def test_voice_note_must_be_audio_and_short() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]
    fake = _post(production, piece_id, audio=_audio(JPEG, "nota.webm"))
    assert (fake.status_code, fake.json()["code"]) == (415, "upload_unsupported")
    long = _post(production, piece_id, audio=_audio(WEBM + b"\x00" * (2 * 1024 * 1024), "x.webm"))
    assert long.status_code in {413, 422}  # pasa el tope del JSON (422) o el del audio (413)
