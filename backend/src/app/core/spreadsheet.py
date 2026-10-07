"""Leer planillas subidas por el usuario (XLSX o CSV) como dato no confiable.

Límites de tamaño (comprimido y sin comprimir), de hojas, filas y columnas; el XML se parsea
con defusedxml (openpyxl lo usa si está instalado) y nunca se evalúan fórmulas: se lee el
último valor que guardó Excel. También el parser numérico es-AR (PRODUCT_SPEC §7.1).
"""

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from openpyxl import load_workbook

from app.core.errors import AppError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024
MAX_SHEETS = 40
MAX_ROWS = 5000
MAX_COLUMNS = 40


@dataclass(frozen=True)
class Sheet:
    name: str
    rows: list[list[Any]]


def _check_xlsx(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise AppError(422, "import_not_xlsx", "El archivo no es una planilla .xlsx") from exc
    if total > MAX_UNCOMPRESSED_BYTES:
        raise AppError(413, "import_too_large", "La planilla es demasiado grande")


def _xlsx(data: bytes) -> list[Sheet]:
    _check_xlsx(data)
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # cualquier archivo roto es un 422 para el usuario
        raise AppError(422, "import_not_xlsx", "No se pudo leer la planilla") from exc
    try:
        return [
            Sheet(
                name=ws.title,
                rows=[
                    list(row)
                    for row in ws.iter_rows(max_row=MAX_ROWS, max_col=MAX_COLUMNS, values_only=True)
                ],
            )
            for ws in workbook.worksheets[:MAX_SHEETS]
        ]
    finally:
        workbook.close()


def _csv(data: bytes) -> list[Sheet]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")  # Excel en Windows guarda los CSV así
    sample = text[:4096]
    delimiter = max((";", ",", "\t"), key=sample.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for index, row in enumerate(reader):
        if index >= MAX_ROWS:
            break
        rows.append(row[:MAX_COLUMNS])
    return [Sheet(name="CSV", rows=rows)]


def read_spreadsheet(data: bytes, filename: str) -> list[Sheet]:
    """Las hojas del archivo (un CSV es una sola hoja), con los valores de cada celda."""
    if len(data) > MAX_FILE_BYTES:
        raise AppError(413, "import_too_large", "El archivo pesa más de 5 MB")
    if filename.lower().endswith(".csv"):
        return _csv(data)
    return _xlsx(data)


_THOUSANDS_DOT = re.compile(r"^\d{1,3}(\.\d{3})+$")
_THOUSANDS_COMMA = re.compile(r"^\d{1,3}(,\d{3})+$")


def _split_ar(text: str) -> tuple[str, str] | None:
    """Parte entera y decimal de un número es-AR sin signo, o None si no es válido."""
    dot, comma = text.rfind("."), text.rfind(",")
    result: tuple[str, str] | None
    if dot >= 0 and comma >= 0:  # el último separador es el decimal
        decimal_sep, thousands = (".", ",") if dot > comma else (",", ".")
        whole, _, frac = text.rpartition(decimal_sep)
        result = None if thousands in frac else (whole.replace(thousands, ""), frac)
    elif text.count(",") == 1:
        whole, _, frac = text.partition(",")
        result = (whole, frac)
    elif comma >= 0:
        result = (text.replace(",", ""), "") if _THOUSANDS_COMMA.match(text) else None
    elif text.count(".") > 1:
        result = (text.replace(".", ""), "") if _THOUSANDS_DOT.match(text) else None
    elif dot >= 0:
        whole, _, frac = text.partition(".")
        thousands_dot = len(frac) == 3 and whole not in {"", "0"}  # "1.500" → 1500
        result = (whole + frac, "") if thousands_dot else (whole, frac)
    else:
        result = (text, "")
    return result


def parse_decimal_ar(value: Any) -> Decimal | None:
    """Un número de una celda: int/float de Excel o texto es-AR ("1.234,56", "$ 1.500").

    Las reglas son las del parser del frontend: "," decimal y "." de miles; un único "."
    seguido de exactamente 3 dígitos es de miles ("1.500" = 1500).
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    text = str(value).strip().replace("$", "").replace(" ", "").replace("\u00a0", "")
    negative = text.startswith("-")
    text = text.removeprefix("-")
    parts = _split_ar(text) if text and re.fullmatch(r"[\d.,]*\d[\d.,]*", text) else None
    if (
        parts is None
        or not (parts[0].isdigit() or parts[0] == "")
        or not (parts[1].isdigit() or parts[1] == "")
    ):
        return None
    number = Decimal(f"{parts[0] or '0'}.{parts[1] or '0'}")
    return -number if negative else number
