"""PDF de la propuesta (P-03): mismo snapshot que el link, sin datos internos (caso 6)."""

from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import text

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.modules.proposals.pdf import format_money, format_quantity, render_html
from app.modules.proposals.public_schemas import PublicSnapshot
from tests.conftest import make_client
from tests.proposals.test_decisions import BROWSER, _token
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import build_org, logged_in


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)


def _downloads(org_id: object, proposal_id: str) -> int:
    with session_scope(DbContext(organization_id=org_id)) as s:  # type: ignore[arg-type]
        return int(
            s.execute(
                text(
                    "SELECT count(*) FROM proposal_activity "
                    "WHERE proposal_id = :id AND type = 'PDF_DOWNLOADED'"
                ),
                {"id": proposal_id},
            ).scalar_one()
        )


def test_money_and_quantity_format_like_the_frontend() -> None:
    assert format_money("1337050", "ARS") == "$ 1.337.050,00"
    assert format_money("-12.5", "USD") == "-US$ 12,50"
    assert format_money("0.004", "ARS") == "$ 0,00"
    assert format_money(None, "ARS") == ""
    assert (format_quantity("2.5000"), format_quantity("3.0000")) == ("2,5", "3")


def test_public_pdf_has_the_link_content_and_nothing_internal() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    created = _send(owner, world, display_mode="DETAILED", payment_terms="50 % al confirmar")
    url = f"/api/v1/public/proposals/{_token(created)}/pdf"

    response = make_client().get(url, headers=BROWSER)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    number = created["proposal"]["number"]
    assert f'filename="propuesta-{number}.pdf"' in response.headers["content-disposition"]
    content = _text(response.content)
    for expected in (f"Propuesta #{number}", "Cliente ejemplo", "$ 1.694,00", "50 % al confirmar"):
        assert expected in content
    # Costo (1.000), markup (40 %) y proveedor no aparecen en ningún lado.
    for internal in ("1.000,00", "1000", "Proveedor ejemplo", "40 %", "0,4"):
        assert internal not in content
    assert _downloads(world.organization_id, created["proposal"]["id"]) == 1

    # La vista previa de WhatsApp no cuenta como descarga; la productora tampoco.
    make_client().get(url, headers={"User-Agent": "WhatsApp/2"})
    viewer = logged_in(world.members[Role.VIEWER])
    internal = viewer.get(f"/api/v1/proposals/{created['proposal']['id']}/pdf")
    assert internal.status_code == 200
    assert internal.content == response.content  # cacheado por content_hash
    assert _downloads(world.organization_id, created["proposal"]["id"]) == 1

    owner.post(f"/api/v1/proposals/{created['proposal']['id']}/revoke")
    assert make_client().get(url).status_code == 410
    assert make_client().get("/api/v1/public/proposals/" + "x" * 43 + "/pdf").status_code == 404


def test_template_escapes_text_from_the_snapshot() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    created = _send(owner, world)
    snapshot = _ok(make_client().get(f"/api/v1/public/proposals/{_token(created)}"))["proposal"]
    snapshot["organization"]["name"] = 'Org "<b>&'
    snapshot["sections"][0]["items"][0]["description"] = "<script>alert(1)</script>"
    html = render_html(PublicSnapshot.model_validate(snapshot))
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Org &#34;&lt;b&gt;&amp;" in html
