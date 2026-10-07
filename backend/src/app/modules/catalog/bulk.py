"""Aumento masivo (C-10): "Proveedor X subió 8 % desde el 1/11" o "Transporte +12 %".

Crea un registro nuevo en el historial de cada oferta (origen BULK_UPDATE); nunca pisa los
anteriores. Los presupuestos enviados no cambian: sus líneas tienen el costo copiado.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select

from app.core.db import AppSession
from app.core.errors import AppError
from app.core.permissions import Permission
from app.modules.auth import TenantContext
from app.modules.catalog.costs import current_and_upcoming, today_ar
from app.modules.catalog.models import Category, Product, Supplier, SupplierProduct
from app.modules.catalog.schemas import BulkIncreaseIn, BulkItem, BulkPreviewOut, PriceIn
from app.modules.catalog.service import _audit, _category, _record_price, _supplier

CENT = Decimal("0.01")


def _scope_label(db: AppSession, ctx: TenantContext, body: BulkIncreaseIn) -> str:
    parts = []
    if body.supplier_id:
        parts.append(f"proveedor {_supplier(db, ctx, body.supplier_id).name}")
    if body.category_id:
        parts.append(f"categoría {_category(db, ctx, body.category_id).name}")
    return " · ".join(parts)


def _targets(
    db: AppSession, ctx: TenantContext, body: BulkIncreaseIn, valid_from: date
) -> tuple[list[BulkItem], int]:
    query = (
        select(SupplierProduct, Product.name, Supplier.name)
        .join(Product, Product.id == SupplierProduct.product_id)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.organization_id == ctx.organization_id,
            SupplierProduct.is_active.is_(True),
            Product.deleted_at.is_(None),
            Supplier.deleted_at.is_(None),
        )
        .order_by(Product.name, Supplier.name)
    )
    if body.supplier_id:
        query = query.where(SupplierProduct.supplier_id == body.supplier_id)
    if body.category_id:  # la categoría y sus subcategorías
        children = select(Category.id).where(
            Category.parent_id == body.category_id, Category.deleted_at.is_(None)
        )
        query = query.where(
            or_(Product.category_id == body.category_id, Product.category_id.in_(children))
        )
    rows = db.execute(query).all()
    # El costo base es el vigente en la fecha del aumento.
    current, _ = current_and_upcoming(db, [offer.id for offer, _, _ in rows], valid_from)
    items, skipped = [], 0
    for offer, product_name, supplier_name in rows:
        price = current.get(offer.id)
        if price is None:
            skipped += 1  # sin costo cargado: no hay sobre qué aumentar
            continue
        new = (price.amount * (1 + body.rate)).quantize(CENT, rounding=ROUND_HALF_UP)
        items.append(
            BulkItem(
                offer_id=offer.id,
                product_name=product_name,
                supplier_name=supplier_name,
                current=price.amount.quantize(CENT, rounding=ROUND_HALF_UP),
                new=new,
                includes_iva=price.amount_includes_iva,
                iva_rate=price.iva_rate,
            )
        )
    return items, skipped


def _check(ctx: TenantContext, body: BulkIncreaseIn) -> date:
    if not ctx.can(Permission.COSTS_EDIT):
        raise AppError(403, "permission_denied", "No tenés permiso para cambiar costos")
    return body.valid_from or today_ar()


def preview_bulk(db: AppSession, ctx: TenantContext, body: BulkIncreaseIn) -> BulkPreviewOut:
    valid_from = _check(ctx, body)
    scope = _scope_label(db, ctx, body)
    items, skipped = _targets(db, ctx, body, valid_from)
    return BulkPreviewOut(
        scope=scope, valid_from=valid_from, items=items, skipped_without_cost=skipped
    )


def apply_bulk(db: AppSession, ctx: TenantContext, body: BulkIncreaseIn) -> BulkPreviewOut:
    valid_from = _check(ctx, body)
    scope = _scope_label(db, ctx, body)
    items, skipped = _targets(db, ctx, body, valid_from)
    if not items:
        raise AppError(422, "bulk_nothing_to_update", "No hay ofertas con costo para aumentar")
    reference = body.note or f"Aumento {body.rate * 100:+.2f} % · {scope}"
    offers = {
        o.id: o
        for o in db.execute(
            select(SupplierProduct).where(SupplierProduct.id.in_([i.offer_id for i in items]))
        ).scalars()
    }
    for item in items:
        _record_price(
            db,
            ctx,
            offers[item.offer_id],
            PriceIn(
                amount=item.new,
                includes_iva=item.includes_iva,
                iva_rate=item.iva_rate,
                valid_from=valid_from,
                source_ref=reference[:200],
            ),
            "BULK_UPDATE",
        )
    first = next(iter(offers.values()))
    _audit(
        db,
        ctx,
        "catalog.bulk_increase",
        "supplier_product",
        first.id,
        after={
            "scope": scope,
            "rate": str(body.rate),
            "valid_from": valid_from.isoformat(),
            "offers": len(items),
        },
    )
    return BulkPreviewOut(
        scope=scope, valid_from=valid_from, items=items, skipped_without_cost=skipped
    )
