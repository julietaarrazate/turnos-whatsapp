"""Compartir por email al generar (P-04) y exportar a Excel según permisos (3.5)."""

from io import BytesIO

from openpyxl import load_workbook

from app.core.enums import Role
from app.modules.notifications import console_backend
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import build_org, logged_in

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_proposal_link_can_be_emailed_when_generated() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    console_backend.sent.clear()
    created = _send(
        owner,
        world,
        email_to=["Cliente@Banco.example.com", "cliente@banco.example.com", "otra@x.com"],
        email_message="Hola Ana, te paso la propuesta.",
    )
    assert created["emailed_to"] == ["cliente@banco.example.com", "otra@x.com"]
    sent = [m for m in console_backend.sent if m.template == "proposal_sent"]
    assert [m.to for m in sent] == ["cliente@banco.example.com", "otra@x.com"]
    assert sent[0].reply_to == world.members[Role.OWNER].email
    assert created["public_path"] in sent[0].text
    assert sent[0].text.startswith("Hola Ana, te paso la propuesta.")

    too_many = [f"c{i}@x.com" for i in range(6)]
    budget = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}"))
    response = owner.post(
        f"/api/v1/budgets/{world.ids['budget_id']}/proposals",
        json={"email_to": too_many, "version_no": budget["version"]["version_no"]},
    )
    assert response.status_code == 422


def _sheet(response: object) -> list[list[object]]:
    content = response.content  # type: ignore[attr-defined]
    ws = load_workbook(BytesIO(content)).worksheets[0]
    return [list(row) for row in ws.iter_rows(values_only=True)]


def test_excel_export_respects_cost_and_margin_permissions() -> None:
    world = build_org("a")
    url = f"/api/v1/budgets/{world.ids['budget_id']}/versions/1/export.xlsx"

    owner = logged_in(world.members[Role.OWNER])
    response = owner.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == XLSX
    assert "presupuesto-" in response.headers["content-disposition"]
    rows = _sheet(response)
    header = next(r for r in rows if r and r[0] == "Sección")
    assert {"Costo total", "Ganancia", "Margen", "Venta"} <= set(header)
    line = rows[rows.index(header) + 1]
    assert line[header.index("Ítem")] == "Producto ejemplo"
    assert line[header.index("Costo total")] == 1000
    assert line[header.index("Venta")] == 1400
    labels = {r[header.index("Venta") - 1]: r[header.index("Venta")] for r in rows if any(r)}
    assert labels["Total"] == 1694

    # Producción ve costos pero nunca márgenes; un viewer, ninguno de los dos.
    production = _sheet(logged_in(world.members[Role.PRODUCTION]).get(url))
    production_header = next(r for r in production if r and r[0] == "Sección")
    assert "Costo total" in production_header
    assert not {"Ganancia", "Margen", "Markup"} & set(production_header)
    viewer = _sheet(logged_in(world.members[Role.VIEWER]).get(url))
    viewer_header = next(r for r in viewer if r and r[0] == "Sección")
    assert not {"Costo total", "Costo unitario", "Ganancia", "Margen"} & set(viewer_header)
    assert all("Costo directo" not in r for r in viewer)

    actions = {e["action"] for e in _ok(owner.get("/api/v1/audit-logs"))["items"]}
    assert "budget.exported" in actions
    other = build_org("b")
    stranger = logged_in(other.members[Role.OWNER])
    assert stranger.get(url).status_code == 404
