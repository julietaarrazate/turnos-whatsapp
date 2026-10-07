"""Leer un presupuesto desde la planilla de la productora piloto (docs/product/PILOT_NOTES.md).

Formato: una hoja por evento. A la izquierda, el presupuesto al cliente por rubros (cada rubro
abre con una fila de encabezados: DETALLE, Q, JORNADAS, PRECIO UNITARIO, PRECIO TOTAL); a la
derecha, la "META" interna (proveedor / observaciones, costo unitario, costo total, Nº de factura,
condición de pago). Al pie: SUBTOTAL, FEE MANAGEMENT (%) y notas.

El archivo lo sube el usuario: es dato no confiable. Se limita el tamaño (comprimido y sin
comprimir), las hojas, filas y columnas que se leen, y openpyxl parsea el XML con defusedxml.
Solo se leen valores (nunca se evalúan fórmulas: se usa el último valor que guardó Excel).
"""

import unicodedata
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

from app.core.errors import AppError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024
MAX_SHEETS = 40
MAX_ROWS = 2000
MAX_COLUMNS = 40
MAX_LINES = 500

CENT = Decimal("0.01")

# Encabezado normalizado → campo. "PRECIO TOTAL" a veces está pisado (p. ej. con "*"): si
# falta, se toma la columna a la derecha del precio unitario.
_HEADERS = {
    "DETALLE": "detail",
    "Q": "quantity",
    "CANTIDAD": "quantity",
    "JORNADAS": "days",
    "DIAS": "days",
    "PRECIO UNITARIO": "unit_price",
    "PRECIO TOTAL": "total",
    "PROVEEDOR / OBSERVACIONES": "supplier",
    "PROVEEDOR": "supplier",
    "COSTO UNITARIO": "unit_cost",
    "COSTO TOTAL": "cost_total",
    "NOFC": "invoice",
    "NO FC": "invoice",
    "N FC": "invoice",
    "CONDICION DE PAGO": "payment_terms",
}
_BONIFICADO = {"BONIFICADO", "BONIF", "SIN CARGO"}
_A_DEFINIR = {"TBD", "A DEFINIR", "A CONFIRMAR"}


@dataclass(frozen=True)
class SheetLine:
    name: str
    description: str | None
    quantity: Decimal
    days: int
    sale_total: Decimal
    price_label: str | None  # BONIFICADO / A_DEFINIR
    cost_amount: Decimal
    cost_is_total: bool
    notes: str | None


@dataclass(frozen=True)
class SheetSection:
    title: str
    lines: tuple[SheetLine, ...]


@dataclass(frozen=True)
class SheetBudget:
    sheet: str
    title_hint: str
    sections: tuple[SheetSection, ...]
    management_fee_rate: Decimal
    sheet_subtotal: Decimal | None  # lo que dice la fila SUBTOTAL, para comparar
    sheet_fee: Decimal | None
    notes: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def subtotal(self) -> Decimal:
        return sum((ln.sale_total for s in self.sections for ln in s.lines), Decimal(0))

    @property
    def line_count(self) -> int:
        return sum(len(s.lines) for s in self.sections)


@dataclass
class _Columns:
    name: int
    found: dict[str, int] = field(default_factory=dict)

    def get(self, row: tuple[Any, ...], key: str) -> Any:
        index = self.found.get(key)
        return row[index] if index is not None and index < len(row) else None


def _norm(value: Any) -> str:
    """Texto comparable: sin tildes, mayúsculas, espacios simples."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()  # "Nº" → "No"
    return " ".join(text.upper().split())


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _number(value: Any) -> Decimal | None:
    """Número de una celda (int o float de openpyxl) como Decimal, sin pasar por float."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        try:
            return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
        except InvalidOperation:  # pragma: no cover - nan / inf
            return None
    return None


def _ar(amount: Decimal) -> str:
    """$ 1.234.567,89 para los avisos."""
    integer, _, cents = f"{amount.quantize(CENT):.2f}".partition(".")
    return f"$ {int(integer):,}".replace(",", ".") + f",{cents}"


def _label(*values: Any) -> str | None:
    for value in values:
        text = _norm(value)
        if text in _BONIFICADO:
            return "BONIFICADO"
        if text in _A_DEFINIR:
            return "A_DEFINIR"
    return None


def _header(row: tuple[Any, ...]) -> _Columns | None:
    normalized = [_norm(v) for v in row]
    if "DETALLE" not in normalized or not ({"Q", "CANTIDAD"} & set(normalized)):
        return None
    detail = normalized.index("DETALLE")
    if detail == 0:
        return None
    columns = _Columns(name=detail - 1)
    for index, text in enumerate(normalized):
        key = _HEADERS.get(text)
        if key and key not in columns.found:
            columns.found[key] = index
    if "total" not in columns.found and "unit_price" in columns.found:
        columns.found["total"] = columns.found["unit_price"] + 1
    return columns


def _title_hint(rows: list[tuple[Any, ...]], sheet: str) -> str:
    for row in rows[:12]:
        for value in row:
            text = _text(value)
            if text and "PPTO" in _norm(text):
                head = text.split("/")[0].strip(" -")
                if head:
                    return head[:200]
    return sheet[:200]


def _sale(
    total_cell: Any, unit_cell: Any, units: Decimal, *, name: str, detail: str | None
) -> tuple[Decimal, str | None, str | None]:
    """Precio de venta de la línea, etiqueta ("Bonificado" / "A definir") y un aviso si hace
    falta. Manda el PRECIO TOTAL; si no tiene valor, unitario × Q × jornadas."""
    label = _label(total_cell, unit_cell)
    total, unit = _number(total_cell), _number(unit_cell)
    to_define = bool(detail and "DEFINIR" in _norm(detail))
    warning = None
    if label is not None:
        sale = Decimal(0)
    elif total is not None:
        sale = total
    elif unit is not None:
        sale = unit * units
        # Vacío o una fórmula que Excel nunca calculó (openpyxl lee el último valor guardado).
        warning = f"{name}: sin precio total; se calculó Q × jornadas × unitario."
    else:
        sale = Decimal(0)
        warning = None if to_define else f"{name}: no tiene precio; queda en $ 0."
    if sale < 0:
        return Decimal(0), label, f"{name}: precio negativo; queda en $ 0."
    if label is None and sale == 0 and to_define:
        label = "A_DEFINIR"
    return sale, label, warning


def _cost(cost_total: Decimal | None, unit_cost: Decimal | None) -> tuple[Decimal, bool]:
    """El COSTO TOTAL de la META (lo que cotizó el proveedor por la línea) o, si falta, el
    unitario."""
    if cost_total is not None and cost_total >= 0:
        return cost_total, True
    if unit_cost is not None and unit_cost >= 0:
        return unit_cost, False
    return Decimal(0), True


def _notes(row: tuple[Any, ...], cols: _Columns, name: str) -> str | None:
    notes = []
    supplier = _text(cols.get(row, "supplier"))
    if supplier and _norm(supplier) != _norm(name):
        notes.append(f"Proveedor / observaciones: {supplier}")
    for key, label in (("invoice", "Factura"), ("payment_terms", "Condición de pago")):
        value = _text(cols.get(row, key))
        if value:
            notes.append(f"{label}: {value}")
    return "\n".join(notes)[:2000] if notes else None


def _line(row: tuple[Any, ...], cols: _Columns, name: str, warnings: list[str]) -> SheetLine:
    detail = _text(cols.get(row, "detail"))
    quantity = _number(cols.get(row, "quantity"))
    if quantity is None or quantity <= 0:
        quantity = Decimal(1)
    raw_days = _number(cols.get(row, "days"))
    days = min(int(raw_days), 365) if raw_days is not None and raw_days >= 1 else 1
    sale, label, warning = _sale(
        cols.get(row, "total"),
        cols.get(row, "unit_price"),
        quantity * days,
        name=name,
        detail=detail,
    )
    if warning:
        warnings.append(warning)
    cost, is_total = _cost(
        _number(cols.get(row, "cost_total")), _number(cols.get(row, "unit_cost"))
    )
    return SheetLine(
        name=name[:200],
        description=detail[:2000] if detail and detail != name else None,
        quantity=quantity.quantize(Decimal("0.0001")),
        days=days,
        sale_total=sale.quantize(CENT),
        price_label=label,
        cost_amount=cost.quantize(Decimal("0.000001")),
        cost_is_total=is_total,
        notes=_notes(row, cols, name),
    )


class _SheetParser:
    """Recorre la hoja de arriba abajo: rubros (encabezado + ítems), y al pie SUBTOTAL, FEE,
    COSTO IMPOSITIVO y NOTA."""

    def __init__(self) -> None:
        self.sections: list[SheetSection] = []
        self.current: tuple[str, list[SheetLine]] | None = None
        self.cols: _Columns | None = None
        self.warnings: list[str] = []
        self.notes: list[str] = []
        self.fee_rate = Decimal(0)
        self.sheet_subtotal: Decimal | None = None
        self.sheet_fee: Decimal | None = None
        self.footer = False
        self.in_notes = False
        self.count = 0

    def close(self) -> None:
        if self.current is not None:
            title, lines = self.current
            self.sections.append(SheetSection(title=title, lines=tuple(lines)))
        self.current = None

    def footer_row(self, key: str, row: tuple[Any, ...], cols: _Columns) -> bool:
        """Filas del pie. Devuelve True si la fila era del pie."""
        if key.startswith("SUBTOTAL"):
            self.close()
            self.footer = True
            self.sheet_subtotal = _number(cols.get(row, "total"))
        elif key.startswith("FEE"):
            rate = _number(cols.get(row, "detail"))
            if rate is not None and 0 <= rate < 1:
                self.fee_rate = rate.quantize(Decimal("0.000001"))
            elif rate is not None:
                self.warnings.append("El fee de gestión no es un porcentaje válido; quedó en 0.")
            self.sheet_fee = _number(cols.get(row, "total"))
        elif key.startswith("COSTO IMPOSITIVO"):
            if _number(cols.get(row, "detail")):
                self.warnings.append(
                    "La planilla tiene un costo impositivo sobre la venta: cargalo en "
                    "Configuración → Cargos sobre la venta (no se importa por presupuesto)."
                )
        elif key in {"NOTA", "NOTAS"}:
            self.in_notes = True
        else:
            return False
        return True

    def row(self, row: tuple[Any, ...]) -> bool:
        """Procesa una fila. Devuelve False cuando hay que dejar de leer."""
        header = None if self.footer else _header(row)
        if header is not None:
            self.close()
            self.cols = header
            self.current = ((_text(row[header.name]) or "Sin rubro")[:200], [])
            return True
        if self.cols is None or self.in_notes:
            if self.in_notes:
                self.notes.extend(t for t in (_text(v) for v in row) if t)
            return True
        name = _text(row[self.cols.name]) if self.cols.name < len(row) else None
        if self.footer_row(_norm(name), row, self.cols) or self.current is None or not name:
            return True
        if self.count >= MAX_LINES:
            self.warnings.append(f"Se importaron las primeras {MAX_LINES} líneas.")
            return False
        self.current[1].append(_line(row, self.cols, name, self.warnings))
        self.count += 1
        return True


def _parse_sheet(sheet_name: str, rows: list[tuple[Any, ...]]) -> SheetBudget | None:
    parser = _SheetParser()
    for row in rows:
        if not parser.row(row):
            break
    parser.close()
    sections = [s for s in parser.sections if s.lines]
    if not sections:
        return None
    subtotal = sum((ln.sale_total for s in sections for ln in s.lines), Decimal(0))
    sheet_subtotal = parser.sheet_subtotal
    if sheet_subtotal is not None and sheet_subtotal.quantize(CENT) != subtotal:
        parser.warnings.append(
            f"La fila SUBTOTAL de la planilla dice {_ar(sheet_subtotal)} pero los ítems suman "
            f"{_ar(subtotal)}: revisá si la fórmula del subtotal deja afuera alguna fila. "
            "Se importan todos los ítems."
        )
    return SheetBudget(
        sheet=sheet_name[:120],
        title_hint=_title_hint(rows, sheet_name),
        sections=tuple(sections),
        management_fee_rate=parser.fee_rate,
        sheet_subtotal=sheet_subtotal.quantize(CENT) if sheet_subtotal is not None else None,
        sheet_fee=parser.sheet_fee.quantize(CENT) if parser.sheet_fee is not None else None,
        notes=tuple(n[:500] for n in parser.notes[:20]),
        warnings=tuple(dict.fromkeys(parser.warnings)),
    )


def _check_zip(data: bytes) -> None:
    if len(data) > MAX_FILE_BYTES:
        raise AppError(413, "import_too_large", "La planilla pesa más de 5 MB")
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise AppError(422, "import_not_xlsx", "El archivo no es una planilla .xlsx") from exc
    if total > MAX_UNCOMPRESSED_BYTES:
        raise AppError(413, "import_too_large", "La planilla es demasiado grande")


def parse_workbook(data: bytes) -> list[SheetBudget]:
    """Las hojas que tienen el formato de presupuesto, en el orden del libro."""
    _check_zip(data)
    try:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # cualquier archivo roto es un 422 para el usuario
        raise AppError(422, "import_not_xlsx", "No se pudo leer la planilla") from exc
    try:
        found = []
        for worksheet in workbook.worksheets[:MAX_SHEETS]:
            rows = [
                tuple(row)
                for row in worksheet.iter_rows(
                    max_row=MAX_ROWS, max_col=MAX_COLUMNS, values_only=True
                )
            ]
            parsed = _parse_sheet(worksheet.title, rows)
            if parsed is not None:
                found.append(parsed)
    finally:
        workbook.close()
    return found


def pick_sheet(data: bytes, sheet: str | None) -> tuple[SheetBudget, list[str]]:
    sheets = parse_workbook(data)
    if not sheets:
        raise AppError(
            422,
            "import_no_budget",
            "No encontramos un presupuesto en la planilla (rubros con DETALLE, Q y PRECIO)",
        )
    names = [s.sheet for s in sheets]
    if sheet is None:
        return sheets[0], names
    for parsed in sheets:
        if parsed.sheet == sheet:
            return parsed, names
    raise AppError(422, "import_sheet_not_found", "Esa hoja no tiene un presupuesto")
