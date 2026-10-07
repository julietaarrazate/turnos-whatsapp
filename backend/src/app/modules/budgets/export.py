"""Exportar una versión a Excel (3.5). Se arma desde `BudgetOut`, que ya viene filtrado por
permisos: sin `cost.view` no hay columnas de costo y sin `margin.view` no hay márgenes."""

from collections.abc import Callable
from decimal import Decimal
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.modules.budgets.schemas import BudgetOut, LineOut

MONEY = "#,##0.00"
PERCENT = "0.0%"
QUANTITY = "#,##0.####"
_HEADER = PatternFill("solid", fgColor="EEF0FB")
_BOLD = Font(bold=True)

Column = tuple[str, Callable[[str, LineOut], Any], str | None, int]


def _columns(costs: bool, margins: bool) -> list[Column]:
    columns: list[Column] = [
        ("Sección", lambda section, _: section, None, 18),
        ("Ítem", lambda _, line: line.name_internal, None, 32),
        ("Descripción para el cliente", lambda _, line: line.description_client, None, 36),
        ("Proveedor", lambda _, line: line.supplier_name, None, 20),
        ("Unidad", lambda _, line: line.unit_code, None, 8),
        ("Cantidad", lambda _, line: line.quantity, QUANTITY, 10),
        ("Días", lambda _, line: line.days, "0", 6),
    ]
    if costs:
        columns += [
            ("Costo unitario", lambda _, ln: ln.cost and ln.cost.unit_cost_effective, MONEY, 14),
            ("Costo total", lambda _, line: line.cost and line.cost.cost_total, MONEY, 14),
        ]
    if margins:
        columns += [
            ("Markup", lambda _, line: line.margin and line.margin.markup_applied, PERCENT, 9),
            ("Ganancia", lambda _, line: line.margin and line.margin.profit, MONEY, 14),
            ("Margen", lambda _, line: line.margin and line.margin.margin, PERCENT, 9),
        ]
    columns += [
        ("Descuento", lambda _, line: line.discount_rate or None, PERCENT, 10),
        ("Venta", lambda _, line: line.sale_total, MONEY, 16),
        ("En la propuesta", lambda _, line: "Sí" if line.show_on_proposal else "No", None, 10),
    ]
    return columns


def version_xlsx(budget: BudgetOut) -> bytes:
    version = budget.version
    costs = version.costs is not None
    margins = version.margins is not None
    columns = _columns(costs, margins)

    wb = Workbook()
    ws = wb.worksheets[0]
    ws.title = f"v{version.version_no}"
    event = budget.event
    state = "borrador" if version.status == "DRAFT" else "guardada"
    for row in (
        (f"Presupuesto #{budget.number} — {budget.title}",),
        (f"Cliente: {event.client_name} · Evento: {event.name}",),
        (f"Versión {version.version_no} ({state}) · Moneda: {budget.currency}",),
        (),
    ):
        ws.append(row)
    ws["A1"].font = Font(bold=True, size=13)

    header_row = ws.max_row + 1
    ws.append([title for title, *_ in columns])
    for index, (_, _, _, width) in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=index)
        cell.font = _BOLD
        cell.fill = _HEADER
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    for section in version.sections:
        for line in section.lines:
            ws.append([value(section.title_client, line) for _, value, _, _ in columns])
            for index, (_, _, number_format, _) in enumerate(columns, start=1):
                if number_format:
                    ws.cell(row=ws.max_row, column=index).number_format = number_format

    ws.append([])
    label_column = len(columns) - 2  # rótulo a la izquierda de "Venta"
    totals: list[tuple[str, Decimal | None, str]] = [
        ("Subtotal", version.sale_subtotal, MONEY),
        ("Descuento global", -version.global_discount if version.global_discount else None, MONEY),
        ("Fee de gestión", version.management_fee or None, MONEY),
        ("Neto", version.sale_net, MONEY),
        ("IVA", version.iva, MONEY),
        ("Total", version.total, MONEY),
    ]
    if version.costs is not None:
        totals.append(("Costo directo", version.costs.cost_direct, MONEY))
    if version.margins is not None:
        totals += [
            ("Cargos sobre la venta", version.margins.sale_charges, MONEY),
            ("Ganancia", version.margins.profit, MONEY),
            ("Margen neto", version.margins.margin_net, PERCENT),
        ]
    for label, amount, number_format in totals:
        if amount is None:
            continue
        row = ws.max_row + 1
        ws.cell(row=row, column=label_column, value=label).font = _BOLD
        cell = ws.cell(row=row, column=label_column + 1, value=amount)
        cell.number_format = number_format
        if label == "Total":
            cell.font = _BOLD

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
