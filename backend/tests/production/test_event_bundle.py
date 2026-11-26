"""Descargar todo el evento en un .zip ordenado en carpetas."""

import io
import zipfile
from base64 import b64encode

from app.core.enums import Role
from app.modules.production.bundle import safe_name
from tests.production.test_event_files import JPEG, PDF, _add
from tests.proposals.test_proposals import _ok
from tests.security.harness import build_org, logged_in


def test_everything_in_folders_and_links_in_the_readme() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]
    file = {"filename": "brief.pdf", "file_base64": b64encode(PDF).decode()}
    _ok(_add(production, world, category="CLIENT", title="Brief: Natura/2026", file=file), 201)
    _ok(_add(production, world, category="CLIENT", title="Brief: Natura/2026", file=file), 201)
    plan = {"title": "Plano de corte", "filename": "p.pdf", "file_base64": b64encode(PDF).decode()}
    _ok(production.post(f"/api/v1/pieces/{piece_id}/plans", json=plan), 201)
    photo = {"filename": "f.jpg", "file_base64": b64encode(JPEG).decode()}
    _ok(production.post(f"/api/v1/pieces/{piece_id}/updates", json={"photo": photo}), 201)

    viewer = logged_in(world.members[Role.VIEWER])
    response = viewer.get(f"/api/v1/events/{world.ids['event_id']}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    bundle = zipfile.ZipFile(io.BytesIO(response.content))
    names = bundle.namelist()

    assert "01 Del cliente/Brief Natura 2026.pdf" in names
    assert "01 Del cliente/Brief Natura 2026 (2).pdf" in names
    assert bundle.read("01 Del cliente/Brief Natura 2026.pdf") == PDF
    assert any(n.startswith("03 Planos/") and n.endswith("Plano de corte v1.pdf") for n in names)
    assert any(n.startswith("04 Avances/") for n in names)
    readme = bundle.read("Léeme.txt").decode()
    assert "Manual de marca" in readme  # el link del harness
    assert "https://drive.google.com/" in readme
    # Sin permiso de costos, no van los comprobantes.
    assert not any(n.startswith("07 Comprobantes/") for n in names)


def test_other_organization_gets_404() -> None:
    world = build_org("a")
    stranger = logged_in(build_org("b").members[Role.OWNER])
    assert stranger.get(f"/api/v1/events/{world.ids['event_id']}/download").status_code == 404


def test_names_work_on_any_computer() -> None:
    assert safe_name('Render: final/v2*?"') == "Render final v2"
    assert safe_name("   ") == "archivo"
    assert safe_name("Diseño ñandú") == "Diseño ñandú"
