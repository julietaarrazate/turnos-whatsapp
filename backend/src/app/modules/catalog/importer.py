"""Importar el catálogo desde XLSX o CSV (C-09, journey J1).

Sube el archivo → se detectan los encabezados y se sugiere el mapeo de columnas → vista previa
con errores por fila (simulación, no guarda nada) → confirmar. Se crean categorías,
proveedores, productos, ofertas y costos (origen IMPORT). Volver a importar el mismo archivo no
duplica: los productos se buscan por nombre y un costo igual al vigente no se vuelve a cargar.
"""

import unicodedata
from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.core.db import AppSession
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.spreadsheet import Sheet, parse_decimal_ar, read_spreadsheet
from app.domain.pricing import ChargeMode
from app.modules.auth import TenantContext
from app.modules.catalog.costs import current_and_upcoming, today_ar
from app.modules.catalog.models import Category, Product, Supplier, SupplierProduct, Unit
from app.modules.catalog.schemas import (
    CatalogImportIn,
    CatalogImportOut,
    ImportField,
    ImportRowOut,
    ImportSummary,
    PriceIn,
)
from app.modules.catalog.service import _audit, _record_price, _set_preferred

PREVIEW_ROWS = 300
DEFAULT_CATEGORY = "Sin categoría"

# Encabezados que se reconocen solos (sin tildes, en minúscula) → campo.
_HEADER_HINTS: dict[ImportField, tuple[str, ...]] = {
    ImportField.NAME: ("producto", "nombre", "item", "articulo", "servicio"),
    ImportField.CATEGORY: ("categoria", "rubro"),
    ImportField.SUPPLIER: ("proveedor",),
    ImportField.UNIT: ("unidad", "um", "u/m"),
    ImportField.COST: ("costo", "precio", "precio costo", "costo unitario", "precio unitario"),
    ImportField.INCLUDES_IVA: ("incluye iva", "con iva", "iva incluido"),
    ImportField.IVA_RATE: ("iva", "alicuota", "% iva", "alicuota iva"),
    ImportField.CHARGE_MODE: ("cobro", "modo de cobro", "por dia"),
    ImportField.DESCRIPTION_CLIENT: ("descripcion", "descripcion cliente", "detalle"),
    ImportField.SUPPLIER_SKU: ("codigo", "sku", "cod proveedor", "codigo proveedor"),
}
_YES = {"si", "sí", "s", "x", "true", "1", "verdadero", "incluye", "con iva"}
_PER_DAY = {"dia", "por dia", "diario", "jornada", "por jornada", "per_day"}


def _norm(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace(":", "").split())


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _header_row(sheet: Sheet) -> int:
    """La primera fila con al menos dos celdas de texto."""
    for index, row in enumerate(sheet.rows[:20]):
        if sum(1 for v in row if isinstance(v, str) and v.strip()) >= 2:
            return index
    return 0


def suggest_mapping(headers: list[str]) -> dict[ImportField, int | None]:
    normalized = [_norm(h) for h in headers]
    mapping: dict[ImportField, int | None] = {}
    taken: set[int] = set()
    for field_name, hints in _HEADER_HINTS.items():
        index = next((i for i, h in enumerate(normalized) if h in hints and i not in taken), None)
        if index is not None:
            taken.add(index)
        mapping[field_name] = index
    return mapping


@dataclass
class _Lookups:
    categories: dict[str, Category]
    suppliers: dict[str, Supplier]
    products: dict[str, Product]
    units: dict[str, Unit]
    default_unit: Unit
    offers: dict[tuple[Any, Any], SupplierProduct] = field(default_factory=dict)


def _lookups(db: AppSession, ctx: TenantContext) -> _Lookups:
    org = ctx.organization_id
    units = list(db.execute(select(Unit).where(Unit.organization_id == org)).scalars())
    by_unit = {}
    for unit in units:
        by_unit[_norm(unit.code)] = unit
        by_unit[_norm(unit.name)] = unit
    default_unit = by_unit.get("u") or units[0]
    offers = db.execute(
        select(SupplierProduct).where(SupplierProduct.organization_id == org)
    ).scalars()
    return _Lookups(
        categories={
            _norm(c.name): c
            for c in db.execute(
                select(Category).where(
                    Category.organization_id == org, Category.deleted_at.is_(None)
                )
            ).scalars()
        },
        suppliers={
            _norm(s.name): s
            for s in db.execute(
                select(Supplier).where(
                    Supplier.organization_id == org, Supplier.deleted_at.is_(None)
                )
            ).scalars()
        },
        products={
            _norm(p.name): p
            for p in db.execute(
                select(Product).where(Product.organization_id == org, Product.deleted_at.is_(None))
            ).scalars()
        },
        units=by_unit,
        default_unit=default_unit,
        offers={(o.product_id, o.supplier_id): o for o in offers},
    )


@dataclass
class _Row:
    number: int  # número de fila en la planilla (1 = primera)
    name: str | None
    category: str | None
    supplier: str | None
    unit: Unit | None
    cost: Decimal | None
    includes_iva: bool
    iva_rate: Decimal
    charge_mode: ChargeMode
    description_client: str | None
    supplier_sku: str | None
    errors: list[str]


def _cell(row: list[Any], mapping: dict[ImportField, int | None], key: ImportField) -> Any:
    index = mapping.get(key)
    return row[index] if index is not None and index < len(row) else None


def _iva(value: Any) -> Decimal | None:
    number = parse_decimal_ar(str(value).replace("%", "")) if value is not None else None
    if number is None:
        return None
    return number / 100 if number >= 1 else number  # "21" o "21 %" → 0,21; "0,21" queda


def _parse_row(
    number: int, row: list[Any], mapping: dict[ImportField, int | None], lookups: _Lookups
) -> _Row | None:
    def get(key: ImportField) -> Any:
        return _cell(row, mapping, key)

    if all(v is None or str(v).strip() == "" for v in row):
        return None  # fila vacía
    errors = []
    name = _text(get(ImportField.NAME))
    if not name:
        errors.append("Falta el nombre del producto")
    elif len(name) > 200:
        errors.append("El nombre tiene más de 200 caracteres")
    unit_text = _text(get(ImportField.UNIT))
    unit = lookups.units.get(_norm(unit_text)) if unit_text else None
    if unit_text and unit is None:
        errors.append(f"Unidad desconocida: {unit_text}")
    raw_cost = get(ImportField.COST)
    cost = parse_decimal_ar(raw_cost) if _text(raw_cost) else None
    if _text(raw_cost) and (cost is None or cost < 0):
        errors.append(f"Costo inválido: {raw_cost}")
        cost = None
    supplier = _text(get(ImportField.SUPPLIER))
    if cost is not None and not supplier:
        errors.append("Un costo necesita proveedor")
    raw_iva = get(ImportField.IVA_RATE)
    iva = _iva(raw_iva) if _text(raw_iva) else Decimal("0.21")
    if iva is None or not Decimal(0) <= iva < 1:
        errors.append(f"IVA inválido: {raw_iva}")
        iva = Decimal("0.21")
    mode = _norm(get(ImportField.CHARGE_MODE))
    return _Row(
        number=number,
        name=name,
        category=_text(get(ImportField.CATEGORY)),
        supplier=supplier[:200] if supplier else None,
        unit=unit,
        cost=cost,
        includes_iva=_norm(get(ImportField.INCLUDES_IVA)) in _YES,
        iva_rate=iva.quantize(Decimal("0.0001")),
        charge_mode=ChargeMode.PER_DAY if mode in _PER_DAY else ChargeMode.FIXED,
        description_client=_text(get(ImportField.DESCRIPTION_CLIENT)),
        supplier_sku=(_text(get(ImportField.SUPPLIER_SKU)) or None),
        errors=errors,
    )


@dataclass
class _Plan:
    headers: list[str]
    mapping: dict[ImportField, int | None]
    rows: list[_Row]
    sheets: list[str]
    sheet: str


def _plan(db: AppSession, ctx: TenantContext, body: CatalogImportIn) -> tuple[_Plan, _Lookups]:
    if not (ctx.can(Permission.CATALOG_EDIT) and ctx.can(Permission.COSTS_EDIT)):
        raise AppError(403, "permission_denied", "No tenés permiso para importar el catálogo")
    try:
        data = b64decode(body.file_base64, validate=True)
    except (Base64Error, ValueError) as exc:
        raise AppError(422, "import_not_xlsx", "El archivo no llegó bien; probá de nuevo") from exc
    sheets = [s for s in read_spreadsheet(data, body.filename) if s.rows]
    if not sheets:
        raise AppError(422, "import_empty", "La planilla está vacía")
    sheet = next((s for s in sheets if s.name == body.sheet), sheets[0])
    header_index = _header_row(sheet)
    headers = [str(v).strip() if v is not None else "" for v in sheet.rows[header_index]]
    mapping = {**suggest_mapping(headers), **(body.mapping or {})}
    if mapping.get(ImportField.NAME) is None:
        raise AppError(
            422, "import_no_name_column", "Indicá qué columna tiene el nombre del producto"
        )
    for index in mapping.values():
        if index is not None and not 0 <= index < len(headers):
            raise AppError(422, "import_bad_mapping", "El mapeo apunta a una columna que no existe")
    lookups = _lookups(db, ctx)
    rows: list[_Row] = []
    seen: dict[tuple[str, str], int] = {}
    for offset, raw in enumerate(sheet.rows[header_index + 1 :], start=header_index + 2):
        parsed = _parse_row(offset, raw, mapping, lookups)
        if parsed is None:
            continue
        if parsed.name:
            key = (_norm(parsed.name), _norm(parsed.supplier))
            if key in seen:
                parsed.errors.append(f"Repetida (igual a la fila {seen[key]})")
            else:
                seen[key] = offset
        rows.append(parsed)
    plan = _Plan(
        headers=headers,
        mapping=mapping,
        rows=rows,
        sheets=[s.name for s in sheets],
        sheet=sheet.name,
    )
    return plan, lookups


def _action(row: _Row, lookups: _Lookups) -> str:
    if row.errors:
        return "ERROR"
    return "UPDATE" if _norm(row.name) in lookups.products else "CREATE"


def _summary(rows: list[_Row], lookups: _Lookups) -> ImportSummary:
    valid = [r for r in rows if not r.errors]
    return ImportSummary(
        rows=len(rows),
        valid=len(valid),
        errors=len(rows) - len(valid),
        products_new=len({_norm(r.name) for r in valid if _norm(r.name) not in lookups.products}),
        suppliers_new=len(
            {
                _norm(r.supplier)
                for r in valid
                if r.supplier and _norm(r.supplier) not in lookups.suppliers
            }
        ),
        categories_new=len(
            {
                _norm(r.category or DEFAULT_CATEGORY)
                for r in valid
                if _norm(r.name) not in lookups.products
                and _norm(r.category or DEFAULT_CATEGORY) not in lookups.categories
            }
        ),
        costs=sum(1 for r in valid if r.cost is not None),
    )


def _out(plan: _Plan, lookups: _Lookups, *, applied: bool, prices: int = 0) -> CatalogImportOut:
    summary = _summary(plan.rows, lookups)
    if applied:
        summary.costs = prices
    return CatalogImportOut(
        sheets=plan.sheets,
        sheet=plan.sheet,
        headers=plan.headers,
        mapping=plan.mapping,
        rows=[
            ImportRowOut(
                row=r.number,
                name=r.name,
                category=r.category,
                supplier=r.supplier,
                unit=r.unit.code if r.unit else None,
                cost=r.cost,
                action=_action(r, lookups),
                errors=r.errors,
            )
            for r in plan.rows[:PREVIEW_ROWS]
        ],
        summary=summary,
        applied=applied,
    )


def preview_import(db: AppSession, ctx: TenantContext, body: CatalogImportIn) -> CatalogImportOut:
    plan, lookups = _plan(db, ctx, body)
    return _out(plan, lookups, applied=False)


def _category_for(db: AppSession, ctx: TenantContext, lookups: _Lookups, name: str) -> Category:
    key = _norm(name)
    if key not in lookups.categories:
        category = Category(organization_id=ctx.organization_id, name=name[:120])
        db.add(category)
        db.flush()
        lookups.categories[key] = category
    return lookups.categories[key]


def _supplier_for(db: AppSession, ctx: TenantContext, lookups: _Lookups, name: str) -> Supplier:
    key = _norm(name)
    if key not in lookups.suppliers:
        supplier = Supplier(organization_id=ctx.organization_id, name=name)
        db.add(supplier)
        db.flush()
        lookups.suppliers[key] = supplier
    return lookups.suppliers[key]


def apply_import(db: AppSession, ctx: TenantContext, body: CatalogImportIn) -> CatalogImportOut:
    plan, lookups = _plan(db, ctx, body)
    preview_lookups = _Lookups(
        categories=dict(lookups.categories),
        suppliers=dict(lookups.suppliers),
        products=dict(lookups.products),
        units=lookups.units,
        default_unit=lookups.default_unit,
    )
    valid_from: date = body.valid_from or today_ar()
    reference = f"Importación {body.filename}"[:200]
    prices = 0
    for row in (r for r in plan.rows if not r.errors):
        name = row.name or ""
        product = lookups.products.get(_norm(name))
        if product is None:
            category = _category_for(db, ctx, lookups, row.category or DEFAULT_CATEGORY)
            product = Product(
                organization_id=ctx.organization_id,
                name=name,
                category_id=category.id,
                unit_id=(row.unit or lookups.default_unit).id,
                charge_mode=row.charge_mode.value,
                description_client=row.description_client,
                iva_rate=None,
            )
            db.add(product)
            db.flush()
            lookups.products[_norm(name)] = product
        if not row.supplier:
            continue
        supplier = _supplier_for(db, ctx, lookups, row.supplier)
        offer = lookups.offers.get((product.id, supplier.id))
        if offer is None:
            has_offers = db.execute(
                select(func.count())
                .select_from(SupplierProduct)
                .where(SupplierProduct.product_id == product.id)
            ).scalar_one()
            offer = SupplierProduct(
                organization_id=ctx.organization_id,
                product_id=product.id,
                supplier_id=supplier.id,
                supplier_sku=row.supplier_sku,
            )
            db.add(offer)
            db.flush()
            if not has_offers:  # la primera oferta del producto es la preferida
                _set_preferred(db, offer)
            lookups.offers[(product.id, supplier.id)] = offer
        if row.cost is None:
            continue
        current = current_and_upcoming(db, [offer.id], valid_from)[0].get(offer.id)
        unchanged = (
            current is not None
            and current.amount == row.cost
            and current.amount_includes_iva == row.includes_iva
            and current.iva_rate == row.iva_rate
        )
        if unchanged:
            continue  # reimportar el mismo archivo no duplica el historial
        _record_price(
            db,
            ctx,
            offer,
            PriceIn(
                amount=row.cost,
                includes_iva=row.includes_iva,
                iva_rate=row.iva_rate,
                valid_from=valid_from,
                source_ref=reference,
            ),
            "IMPORT",
        )
        prices += 1
    summary = _summary(plan.rows, preview_lookups)
    _audit(
        db,
        ctx,
        "catalog.imported",
        "organization",
        ctx.organization_id,
        after={
            "file": body.filename[:200],
            "rows": summary.valid,
            "products_new": summary.products_new,
            "suppliers_new": summary.suppliers_new,
            "costs": prices,
        },
    )
    return _out(plan, preview_lookups, applied=True, prices=prices)
