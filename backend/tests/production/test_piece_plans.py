"""Planos de una pieza: versiones por título, la vigente para el taller, quién sube y quién ve."""

from base64 import b64encode
from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in

PDF_V1 = b"%PDF-1.4 plano de corte v1"
PDF_V2 = b"%PDF-1.4 plano de corte v2 con medidas nuevas"


def _upload(
    client: TestClient, piece_id: Any, title: str, data: bytes, name: str = "plano.pdf"
) -> Any:
    body = {"title": title, "filename": name, "file_base64": b64encode(data).decode()}
    return client.post(f"/api/v1/pieces/{piece_id}/plans", json=body)


def _assign_crew(world: OrgWorld) -> TestClient:
    owner = logged_in(world.members[Role.OWNER])
    crew = str(world.members[Role.CREW].user_id)
    _ok(owner.patch(f"/api/v1/pieces/{world.ids['piece_id']}", json={"assignee_user_id": crew}))
    return logged_in(world.members[Role.CREW])


def test_same_title_is_a_new_version_and_the_newest_is_current() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]

    v1 = _ok(_upload(production, piece_id, "Plano de corte", PDF_V1), 201)
    assert (v1["version"], v1["current"], v1["mime"]) == (1, True, "application/pdf")
    # Mismo título (con otras mayúsculas y espacios): versión 2, se respeta el título original.
    v2 = _ok(_upload(production, piece_id, "  plano  de CORTE ", PDF_V2), 201)
    assert (v2["title"], v2["version"], v2["current"]) == ("Plano de corte", 2, True)
    render = _ok(
        _upload(production, piece_id, "Render", b"\xff\xd8\xff\xe0" + b"0" * 50, "r.jpg"), 201
    )
    assert render["version"] == 1

    listed = _ok(production.get(f"/api/v1/pieces/{piece_id}/plans"))
    assert [(p["title"], p["version"], p["current"]) for p in listed] == [
        ("Plano de corte", 2, True),
        ("Plano de corte", 1, False),
        ("Render", 1, True),
    ]
    old = production.get(f"/api/v1/piece-plans/{v1['id']}/file")
    assert (old.status_code, old.content) == (200, PDF_V1)

    owner = logged_in(world.members[Role.OWNER])
    actions = [e["action"] for e in _ok(owner.get("/api/v1/audit-logs"))["items"]]
    assert actions.count("piece.plan_uploaded") == 3


def test_crew_sees_current_plans_of_their_pieces_only() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]
    _ok(_upload(production, piece_id, "Plano de corte", PDF_V1), 201)
    v2 = _ok(_upload(production, piece_id, "Plano de corte", PDF_V2), 201)

    crew = logged_in(world.members[Role.CREW])
    assert crew.get(f"/api/v1/pieces/{piece_id}/plans").status_code == 404
    assert crew.get(f"/api/v1/piece-plans/{v2['id']}/file").status_code == 404

    crew = _assign_crew(world)
    work = _ok(crew.get("/api/v1/my-work"))
    assert work["pieces"][0]["plans"] == [{"id": v2["id"], "title": "Plano de corte", "version": 2}]
    assert crew.get(f"/api/v1/piece-plans/{v2['id']}/file").content == PDF_V2
    # El taller mira los planos; los sube producción.
    assert _upload(crew, piece_id, "Mío", PDF_V1).status_code == 403


def test_only_pdf_or_images() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    bad = _upload(
        production, world.ids["piece_id"], "Corte CNC", b"0\nSECTION\n2\nHEADER", "corte.dxf"
    )
    assert (bad.status_code, bad.json()["code"]) == (415, "upload_unsupported")
