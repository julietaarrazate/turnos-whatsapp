"""Importar un presupuesto desde la planilla de la productora piloto (PILOT_NOTES.md).

La planilla de los tests es sintética: tiene la misma estructura que la real (rubros con
encabezados DETALLE / Q / JORNADAS / PRECIO, la META a la derecha, SUBTOTAL, FEE y NOTA),
con nombres e importes inventados.
"""

from base64 import b64encode
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from openpyxl import Workbook

from app.core.enums import Role
from app.core.errors import AppError
from app.modules.budgets.sheet_import import MAX_FILE_BYTES, parse_workbook
from tests.proposals.test_proposals import _ok
from tests.security.harness import build_org, logged_in

HEADER = [
    "DETALLE",
    "Q",
    "JORNADAS",
    "PRECIO UNITARIO",
    "PRECIO TOTAL",
    None,
    "PROVEEDOR / OBSERVACIONES",
    "COSTO UNITARIO",
    "COSTO TOTAL",
    "UTILIDAD",
    "NºFC",
    "CONDICION DE PAGO",
]


def _sheet_rows() -> list[list[Any]]:
    """Columnas como la real: A vacía, B ítem/rubro, C–G venta, I–N META."""
    return [
        [None, None, None, None, None, None, None, None, "PROVEEDOR COTIZADO"],
        [None, " - FERIA DEMO/ ppto venta", None, None, None, None, None, None, "META"],
        [None, "PRODUCCIÓN ", *HEADER],
        [None, "Dirección de proyecto", "Coordinación general", 1, "—", "Bonificado", "Bonificado"],
        [None, "ESCENARIO", *HEADER],
        # Costo total cotizado por la línea (no por unidad), proveedor distinto del ítem.
        [
            None,
            "Vallas x 10",
            "Perímetro",
            10,
            1,
            1000,
            10000,
            None,
            "Vallas x 12 (Rental SA)",
            None,
            6000,
            "=G6-K6",
            "A-0001-00000123",
            "echeck 30 días",
        ],
        # Por día (2 jornadas): el total es una fórmula sin valor guardado → Q × jornadas × unit.
        [None, "Traslado", "Flete al predio", 3, 2, 500, "=F7*E7*D7", None, "FLETE", 200],
        [None, "Catering", "a definir", 1, 1, 0, 0, None, "CATERING", 0, 0],
        [None, "Varios", *HEADER[:4], "*", *HEADER[5:]],  # "PRECIO TOTAL" pisado con "*"
        [None, "Lonas", "Lonas impresas", 4, 1, 250, 1000, None, None, 150, 600],
        [None, "Seguro", "Según requerimiento", 1, "—", None, "TBD", None, "Seguro", None, 0],
        [None, "SUBTOTAL", None, None, None, None, 10500],  # deja afuera una fila (como la real)
        [],
        [None, "FEE MANAGEMENT ", 0.05, None, None, None, 525],
        [None, "COSTO IMPOSITIVO", 0.03, None, None, None, 0],
        [None, "NOTA"],
        [None, "Válido por 7 días."],
        [None, "Condición de pago: echeck 30 días."],
    ]


def _xlsx(rows: list[list[Any]] | None = None, *, extra_sheet: bool = False) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Feria demo"
    for row in rows if rows is not None else _sheet_rows():
        sheet.append(row)
    if extra_sheet:
        other = workbook.create_sheet("Lista de precios")
        other.append(["Producto", "Precio"])
        workbook.create_sheet("Otro evento").append([None, "RUBRO", *HEADER])
        workbook["Otro evento"].append([None, "Item", "Detalle", 2, 1, 50, 100])
    out = BytesIO()
    workbook.save(out)
    return out.getvalue()


def _b64(data: bytes) -> str:
    return b64encode(data).decode()


def test_parses_sections_prices_costs_fee_and_notes() -> None:
    [budget] = parse_workbook(_xlsx())
    assert budget.sheet == "Feria demo"
    assert budget.title_hint == "FERIA DEMO"
    assert [s.title for s in budget.sections] == ["PRODUCCIÓN", "ESCENARIO", "Varios"]
    lines = {ln.name: ln for s in budget.sections for ln in s.lines}

    assert lines["Dirección de proyecto"].price_label == "BONIFICADO"
    assert lines["Dirección de proyecto"].sale_total == Decimal("0.00")

    vallas = lines["Vallas x 10"]
    assert (vallas.sale_total, vallas.cost_amount, vallas.cost_is_total) == (
        Decimal("10000.00"),
        Decimal("6000.000000"),
        True,
    )
    assert vallas.description == "Perímetro"
    assert vallas.notes == (
        "Proveedor / observaciones: Vallas x 12 (Rental SA)\n"
        "Factura: A-0001-00000123\nCondición de pago: echeck 30 días"
    )

    traslado = lines["Traslado"]
    assert (traslado.quantity, traslado.days, traslado.sale_total) == (
        Decimal("3.0000"),
        2,
        Decimal("3000.00"),
    )
    assert (traslado.cost_amount, traslado.cost_is_total) == (Decimal("200.000000"), False)
    assert lines["Traslado"].notes == "Proveedor / observaciones: FLETE"

    assert lines["Catering"].price_label == "A_DEFINIR"
    assert lines["Seguro"].price_label == "A_DEFINIR"
    assert lines["Lonas"].sale_total == Decimal("1000.00")  # PRECIO TOTAL pisado con "*"

    assert budget.subtotal == Decimal("14000.00")
    assert budget.sheet_subtotal == Decimal("10500.00")
    assert budget.management_fee_rate == Decimal("0.050000")
    assert budget.notes == ("Válido por 7 días.", "Condición de pago: echeck 30 días.")
    warnings = " ".join(budget.warnings)
    assert "Traslado: sin precio total; se calculó Q × jornadas × unitario" in warnings
    assert "SUBTOTAL de la planilla dice $ 10.500,00 pero los ítems suman $ 14.000,00" in warnings
    assert "costo impositivo" in warnings


def test_only_sheets_with_the_budget_format_are_offered() -> None:
    sheets = parse_workbook(_xlsx(extra_sheet=True))
    assert [s.sheet for s in sheets] == ["Feria demo", "Otro evento"]
    assert sheets[1].title_hint == "Otro evento"


def test_rejects_files_that_are_not_a_budget() -> None:
    with pytest.raises(AppError) as not_zip:
        parse_workbook(b"esto no es un excel")
    assert not_zip.value.code == "import_not_xlsx"
    with pytest.raises(AppError) as too_big:
        parse_workbook(b"x" * (MAX_FILE_BYTES + 1))
    assert too_big.value.code == "import_too_large"
    assert parse_workbook(_xlsx([["Producto", "Precio"], ["Algo", 10]])) == []


def test_preview_then_import_creates_the_budget() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    data = _b64(_xlsx(extra_sheet=True))

    preview = _ok(owner.post("/api/v1/budgets/import/preview", json={"file_base64": data}))
    assert preview["sheets"] == ["Feria demo", "Otro evento"]
    assert (preview["sheet"], preview["line_count"]) == ("Feria demo", 6)
    assert (preview["subtotal"], preview["sheet_subtotal"]) == ("14000.00", "10500.00")
    other = _ok(
        owner.post(
            "/api/v1/budgets/import/preview", json={"file_base64": data, "sheet": "Otro evento"}
        )
    )
    assert other["line_count"] == 1

    created = _ok(
        owner.post(
            "/api/v1/budgets/import",
            json={
                "file_base64": data,
                "sheet": "Feria demo",
                "event": {"client_name": "Cliente Demo", "name": "Feria demo", "event_days": 2},
            },
            headers={"Idempotency-Key": "import-1"},
        ),
        201,
    )
    version = created["version"]
    assert [s["title_client"] for s in version["sections"]] == ["PRODUCCIÓN", "ESCENARIO", "Varios"]
    assert version["sale_subtotal"] == "14000.00"  # cada línea con el precio de la planilla
    assert version["management_fee_rate"] == "0.050000"
    assert version["management_fee"] == "700.00"
    lines = {ln["name_internal"]: ln for s in version["sections"] for ln in s["lines"]}
    vallas = lines["Vallas x 10"]
    assert (vallas["pricing_mode"], vallas["sale_total"]) == ("PRICE", "10000.00")
    assert (vallas["cost"]["cost_total"], vallas["cost"]["cost_is_total"]) == ("6000.00", True)
    assert vallas["margin"]["profit"] == "4000.00"
    assert lines["Traslado"]["charge_mode"] == "PER_DAY"
    assert lines["Traslado"]["cost"]["cost_total"] == "1200.00"  # 200 × 3 × 2
    assert lines["Dirección de proyecto"]["client_price_label"] == "BONIFICADO"
    assert lines["Seguro"]["client_price_label"] == "A_DEFINIR"

    # Reintentar con la misma clave no duplica.
    again = owner.post(
        "/api/v1/budgets/import",
        json={
            "file_base64": data,
            "sheet": "Feria demo",
            "event": {"client_name": "Cliente Demo", "name": "Feria demo", "event_days": 2},
        },
        headers={"Idempotency-Key": "import-1"},
    )
    assert again.json()["id"] == created["id"]

    # Para un evento que ya existe.
    existing = _ok(
        owner.post(
            "/api/v1/budgets/import",
            json={"file_base64": data, "event_id": str(world.ids["event_id"])},
        ),
        201,
    )
    assert existing["event"]["id"] == str(world.ids["event_id"])


def test_import_errors_and_permissions() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    bad = owner.post("/api/v1/budgets/import/preview", json={"file_base64": "no es base64!!"})
    assert (bad.status_code, bad.json()["code"]) == (422, "import_not_xlsx")
    empty = owner.post(
        "/api/v1/budgets/import/preview",
        json={"file_base64": _b64(_xlsx([["Producto", "Precio"]]))},
    )
    assert (empty.status_code, empty.json()["code"]) == (422, "import_no_budget")
    missing = owner.post(
        "/api/v1/budgets/import/preview", json={"file_base64": _b64(_xlsx()), "sheet": "Nada"}
    )
    assert (missing.status_code, missing.json()["code"]) == (422, "import_sheet_not_found")

    # Producción ve costos pero no arma presupuestos; un viewer tampoco.
    for role in (Role.PRODUCTION, Role.VIEWER):
        client = logged_in(world.members[role])
        denied = client.post("/api/v1/budgets/import/preview", json={"file_base64": _b64(_xlsx())})
        assert denied.status_code == 403
