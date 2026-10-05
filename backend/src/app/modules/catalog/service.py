"""Casos de uso del catálogo: categorías, proveedores, productos, ofertas y costos."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.db import AppSession
from app.core.errors import AppError, ensure, not_found
from app.core.permissions import Permission
from app.core.security import utcnow
from app.modules.audit import diff, record
from app.modules.auth import TenantContext
from app.modules.catalog.costs import (
    cost_out,
    current_and_upcoming,
    staleness_days,
    today_ar,
)
from app.modules.catalog.models import (
    Category,
    PriceHistory,
    Product,
    Supplier,
    SupplierCategory,
    SupplierContact,
    SupplierProduct,
    Unit,
)
from app.modules.catalog.schemas import (
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    OfferIn,
    OfferOut,
    OfferUpdate,
    PreferredOffer,
    PriceIn,
    PriceOut,
    ProductIn,
    ProductOut,
    ProductPage,
    ProductSummary,
    ProductUpdate,
    SupplierContactIn,
    SupplierContactOut,
    SupplierIn,
    SupplierOfferOut,
    SupplierOut,
    SupplierSummary,
    SupplierUpdate,
    UnitOut,
)
from app.modules.identity import Organization, User


def _audit(
    db: AppSession,
    ctx: TenantContext,
    action: str,
    entity_type: str,
    entity_id: UUID,
    **changes: Any,
) -> None:
    record(
        db,
        organization_id=ctx.organization_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=ctx.user_id,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
        **changes,
    )


def _jsonable(values: dict[str, Any]) -> dict[str, Any]:
    return {
        k: (str(v) if v is not None and not isinstance(v, str | int | bool) else v)
        for k, v in values.items()
    }


def _flush_unique(db: AppSession, constraint: str, code: str, detail: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        if constraint in str(exc.orig):
            raise AppError(409, code, detail) from exc
        raise


def _stale_after(db: AppSession, ctx: TenantContext) -> int:
    org = ensure(db.get(Organization, ctx.organization_id), "organización")
    return staleness_days(org.settings)


# --- Categorías y unidades -----------------------------------------------------------


def _category(db: AppSession, ctx: TenantContext, category_id: UUID) -> Category:
    category = db.execute(
        select(Category).where(
            Category.id == category_id,
            Category.organization_id == ctx.organization_id,
            Category.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if category is None:
        raise not_found()
    return category


def _category_out(c: Category) -> CategoryOut:
    return CategoryOut(
        id=c.id,
        name=c.name,
        parent_id=c.parent_id,
        default_iva_rate=c.default_iva_rate,
        sort=c.sort,
    )


def list_categories(db: AppSession, ctx: TenantContext) -> list[CategoryOut]:
    rows = db.execute(
        select(Category)
        .where(Category.organization_id == ctx.organization_id, Category.deleted_at.is_(None))
        .order_by(Category.sort, Category.name)
    ).scalars()
    return [_category_out(c) for c in rows]


def _check_parent(
    db: AppSession, ctx: TenantContext, parent_id: UUID | None, self_id: UUID | None = None
) -> None:
    if parent_id is None:
        return
    parent = _category(db, ctx, parent_id)
    if parent.id == self_id or parent.parent_id is not None:
        raise AppError(422, "category_parent_invalid", "Solo se admite un nivel de subcategorías")


def create_category(db: AppSession, ctx: TenantContext, body: CategoryIn) -> CategoryOut:
    _check_parent(db, ctx, body.parent_id)
    category = Category(organization_id=ctx.organization_id, **body.model_dump())
    category.name = category.name.strip()
    db.add(category)
    _flush_unique(db, "uq_categories_org_name", "category_name_taken", "Ya existe esa categoría")
    _audit(db, ctx, "category.created", "category", category.id, after={"name": category.name})
    return _category_out(category)


def update_category(
    db: AppSession, ctx: TenantContext, category_id: UUID, body: CategoryUpdate
) -> CategoryOut:
    category = _category(db, ctx, category_id)
    before = _jsonable({f: getattr(category, f) for f in body.model_fields_set})
    if "parent_id" in body.model_fields_set:
        _check_parent(db, ctx, body.parent_id, category.id)
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field in {"name", "default_iva_rate", "sort"} and value is None:
            continue
        setattr(category, field, value.strip() if field == "name" else value)
    _flush_unique(db, "uq_categories_org_name", "category_name_taken", "Ya existe esa categoría")
    old, new = diff(before, _jsonable({f: getattr(category, f) for f in body.model_fields_set}))
    if new:
        _audit(db, ctx, "category.updated", "category", category.id, before=old, after=new)
    return _category_out(category)


def delete_category(db: AppSession, ctx: TenantContext, category_id: UUID) -> None:
    category = _category(db, ctx, category_id)
    in_use = db.execute(
        select(func.count())
        .select_from(Product)
        .where(Product.category_id == category.id, Product.deleted_at.is_(None))
    ).scalar_one()
    children = db.execute(
        select(func.count())
        .select_from(Category)
        .where(Category.parent_id == category.id, Category.deleted_at.is_(None))
    ).scalar_one()
    if in_use or children:
        raise AppError(409, "category_in_use", "La categoría tiene productos o subcategorías")
    category.deleted_at = utcnow()
    _audit(db, ctx, "category.deleted", "category", category.id)


def list_units(db: AppSession, ctx: TenantContext) -> list[UnitOut]:
    rows = db.execute(
        select(Unit).where(Unit.organization_id == ctx.organization_id).order_by(Unit.name)
    ).scalars()
    return [
        UnitOut(id=u.id, code=u.code, name=u.name, allows_decimals=u.allows_decimals) for u in rows
    ]


# --- Proveedores -------------------------------------------------------------------------

_SUPPLIER_FIELDS = (
    "name",
    "legal_name",
    "tax_id",
    "tax_condition",
    "payment_terms",
    "notes",
    "rating",
    "rating_notes",
)


def _supplier(db: AppSession, ctx: TenantContext, supplier_id: UUID) -> Supplier:
    supplier = db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.organization_id == ctx.organization_id,
            Supplier.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if supplier is None:
        raise not_found()
    return supplier


def _replace_supplier_contacts(
    db: AppSession, ctx: TenantContext, supplier_id: UUID, contacts: list[SupplierContactIn]
) -> None:
    db.execute(delete(SupplierContact).where(SupplierContact.supplier_id == supplier_id))
    primary_seen = False
    for contact in contacts:
        is_primary = contact.is_primary and not primary_seen
        primary_seen = primary_seen or is_primary
        db.add(
            SupplierContact(
                organization_id=ctx.organization_id,
                supplier_id=supplier_id,
                name=contact.name.strip(),
                email=str(contact.email).lower() if contact.email else None,
                phone=contact.phone,
                is_primary=is_primary,
            )
        )


def _replace_supplier_categories(
    db: AppSession, ctx: TenantContext, supplier_id: UUID, category_ids: list[UUID]
) -> None:
    for category_id in set(category_ids):
        _category(db, ctx, category_id)  # 404 si no existe o es de otra organización
    db.execute(delete(SupplierCategory).where(SupplierCategory.supplier_id == supplier_id))
    for category_id in set(category_ids):
        db.add(
            SupplierCategory(
                organization_id=ctx.organization_id,
                supplier_id=supplier_id,
                category_id=category_id,
            )
        )


def _supplier_out(db: AppSession, ctx: TenantContext, supplier: Supplier) -> SupplierOut:
    contacts = db.execute(
        select(SupplierContact)
        .where(SupplierContact.supplier_id == supplier.id)
        .order_by(SupplierContact.is_primary.desc(), SupplierContact.name)
    ).scalars()
    category_ids = db.execute(
        select(SupplierCategory.category_id).where(SupplierCategory.supplier_id == supplier.id)
    ).scalars()
    offers = db.execute(
        select(SupplierProduct, Product, Unit)
        .join(Product, Product.id == SupplierProduct.product_id)
        .join(Unit, Unit.id == Product.unit_id)
        .where(SupplierProduct.supplier_id == supplier.id, Product.deleted_at.is_(None))
        .order_by(Product.name)
    ).all()
    show_cost = ctx.can(Permission.COST_VIEW)
    today, stale_after = today_ar(), _stale_after(db, ctx)
    current, _ = (
        current_and_upcoming(db, [o.id for o, _, _ in offers], today) if show_cost else ({}, {})
    )
    return SupplierOut(
        id=supplier.id,
        name=supplier.name,
        legal_name=supplier.legal_name,
        tax_id=supplier.tax_id,
        tax_condition=supplier.tax_condition,
        payment_terms=supplier.payment_terms,
        notes=supplier.notes,
        rating=supplier.rating,
        rating_notes=supplier.rating_notes,
        is_internal=supplier.is_internal,
        contacts=[
            SupplierContactOut(
                id=c.id, name=c.name, email=c.email, phone=c.phone, is_primary=c.is_primary
            )
            for c in contacts
        ],
        category_ids=list(category_ids),
        offers=[
            SupplierOfferOut(
                offer_id=offer.id,
                product_id=product.id,
                product_name=product.name,
                unit_code=unit.code,
                current_cost=cost_out(current[offer.id], today, stale_after)
                if offer.id in current
                else None,
            )
            for offer, product, unit in offers
        ],
    )


def list_suppliers(db: AppSession, ctx: TenantContext, q: str | None) -> list[SupplierSummary]:
    offers_count = (
        select(func.count())
        .select_from(SupplierProduct)
        .where(SupplierProduct.supplier_id == Supplier.id, SupplierProduct.is_active.is_(True))
        .scalar_subquery()
    )
    query = select(Supplier, offers_count).where(
        Supplier.organization_id == ctx.organization_id, Supplier.deleted_at.is_(None)
    )
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        query = query.where(
            or_(func.lower(Supplier.name).like(pattern), Supplier.tax_id.like(pattern))
        )
    rows = db.execute(query.order_by(Supplier.is_internal.desc(), func.lower(Supplier.name))).all()
    names: dict[UUID, list[str]] = {}
    for supplier_id, name in db.execute(
        select(SupplierCategory.supplier_id, Category.name)
        .join(Category, Category.id == SupplierCategory.category_id)
        .where(SupplierCategory.organization_id == ctx.organization_id)
        .order_by(Category.sort)
    ).all():
        names.setdefault(supplier_id, []).append(name)
    return [
        SupplierSummary(
            id=s.id,
            name=s.name,
            is_internal=s.is_internal,
            rating=s.rating,
            category_names=names.get(s.id, []),
            offers_count=count,
        )
        for s, count in rows
    ]


def get_supplier(db: AppSession, ctx: TenantContext, supplier_id: UUID) -> SupplierOut:
    return _supplier_out(db, ctx, _supplier(db, ctx, supplier_id))


def create_supplier(db: AppSession, ctx: TenantContext, body: SupplierIn) -> SupplierOut:
    supplier = Supplier(
        organization_id=ctx.organization_id, **body.model_dump(include=set(_SUPPLIER_FIELDS))
    )
    supplier.name = supplier.name.strip()
    db.add(supplier)
    _flush_unique(db, "uq_suppliers_org_name", "supplier_name_taken", "Ya existe ese proveedor")
    _replace_supplier_contacts(db, ctx, supplier.id, body.contacts)
    _replace_supplier_categories(db, ctx, supplier.id, body.category_ids)
    db.flush()
    _audit(db, ctx, "supplier.created", "supplier", supplier.id, after={"name": supplier.name})
    return _supplier_out(db, ctx, supplier)


def update_supplier(
    db: AppSession, ctx: TenantContext, supplier_id: UUID, body: SupplierUpdate
) -> SupplierOut:
    supplier = _supplier(db, ctx, supplier_id)
    fields = body.model_fields_set & set(_SUPPLIER_FIELDS)
    before = _jsonable({f: getattr(supplier, f) for f in fields})
    for field in fields:
        value = getattr(body, field)
        if field == "name":
            if value is None:
                raise AppError(422, "name_required", "El nombre es obligatorio")
            value = value.strip()
        setattr(supplier, field, value)
    _flush_unique(db, "uq_suppliers_org_name", "supplier_name_taken", "Ya existe ese proveedor")
    if body.contacts is not None:
        _replace_supplier_contacts(db, ctx, supplier.id, body.contacts)
    if body.category_ids is not None:
        _replace_supplier_categories(db, ctx, supplier.id, body.category_ids)
    db.flush()
    old, new = diff(before, _jsonable({f: getattr(supplier, f) for f in fields}))
    if new or body.contacts is not None or body.category_ids is not None:
        _audit(db, ctx, "supplier.updated", "supplier", supplier.id, before=old, after=new)
    return _supplier_out(db, ctx, supplier)


def delete_supplier(db: AppSession, ctx: TenantContext, supplier_id: UUID) -> None:
    supplier = _supplier(db, ctx, supplier_id)
    if supplier.is_internal:
        raise AppError(409, "internal_supplier", "El proveedor interno no se puede borrar")
    supplier.deleted_at = utcnow()
    db.execute(
        update(SupplierProduct)
        .where(SupplierProduct.supplier_id == supplier.id)
        .values(is_active=False, is_preferred=False)
    )
    _audit(db, ctx, "supplier.deleted", "supplier", supplier.id)


# --- Productos ---------------------------------------------------------------------------

_PRODUCT_FIELDS = (
    "name",
    "category_id",
    "unit_id",
    "charge_mode",
    "description_internal",
    "description_client",
    "min_quantity",
    "iva_rate",
    "is_active",
)


def _product(db: AppSession, ctx: TenantContext, product_id: UUID) -> Product:
    product = db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.organization_id == ctx.organization_id,
            Product.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if product is None:
        raise not_found()
    return product


def _unit(db: AppSession, ctx: TenantContext, unit_id: UUID) -> Unit:
    unit = db.execute(
        select(Unit).where(Unit.id == unit_id, Unit.organization_id == ctx.organization_id)
    ).scalar_one_or_none()
    if unit is None:
        raise not_found()
    return unit


def _offers_out(db: AppSession, ctx: TenantContext, product_id: UUID) -> list[OfferOut]:
    rows = db.execute(
        select(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(SupplierProduct.product_id == product_id)
    ).all()
    show_cost = ctx.can(Permission.COST_VIEW)
    today, stale_after = today_ar(), _stale_after(db, ctx)
    current, upcoming = (
        current_and_upcoming(db, [o.id for o, _ in rows], today) if show_cost else ({}, {})
    )
    offers = [
        OfferOut(
            id=offer.id,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            supplier_is_internal=supplier.is_internal,
            supplier_rating=supplier.rating,
            supplier_sku=offer.supplier_sku,
            is_preferred=offer.is_preferred,
            is_active=offer.is_active,
            notes=offer.notes,
            current_cost=cost_out(current[offer.id], today, stale_after)
            if offer.id in current
            else None,
            upcoming_cost=cost_out(upcoming[offer.id], today, stale_after)
            if offer.id in upcoming
            else None,
        )
        for offer, supplier in rows
    ]
    # "¿Quién me ofrece esto?": activas primero, de menor a mayor costo; sin costo al final.
    return sorted(
        offers,
        key=lambda o: (
            not o.is_active,
            o.current_cost is None,
            o.current_cost.amount if o.current_cost else 0,
            o.supplier_name.lower(),
        ),
    )


def _product_out(db: AppSession, ctx: TenantContext, product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        category_id=product.category_id,
        unit_id=product.unit_id,
        charge_mode=product.charge_mode,
        description_internal=product.description_internal,
        description_client=product.description_client,
        min_quantity=product.min_quantity,
        iva_rate=product.iva_rate,
        is_active=product.is_active,
        offers=_offers_out(db, ctx, product.id),
    )


def list_products(
    db: AppSession,
    ctx: TenantContext,
    *,
    q: str | None,
    category_id: UUID | None,
    include_inactive: bool,
    cursor: str | None,
    limit: int,
) -> ProductPage:
    offers_count = (
        select(func.count())
        .select_from(SupplierProduct)
        .where(SupplierProduct.product_id == Product.id, SupplierProduct.is_active.is_(True))
        .scalar_subquery()
    )
    query = (
        select(Product, Category.name, Unit.code, offers_count)
        .join(Category, Category.id == Product.category_id)
        .join(Unit, Unit.id == Product.unit_id)
        .where(Product.organization_id == ctx.organization_id, Product.deleted_at.is_(None))
    )
    if not include_inactive:
        query = query.where(Product.is_active.is_(True))
    if category_id is not None:
        query = query.where(
            or_(Product.category_id == category_id, Category.parent_id == category_id)
        )
    if q and q.strip():
        query = query.where(func.lower(Product.name).like(f"%{q.strip().lower()}%"))
    if cursor:
        query = query.where(func.lower(Product.name) > cursor)
    rows = db.execute(query.order_by(func.lower(Product.name)).limit(limit + 1)).all()
    page = rows[:limit]

    preferred_rows = db.execute(
        select(SupplierProduct, Supplier.name)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.product_id.in_([p.id for p, *_ in page]),
            SupplierProduct.is_preferred.is_(True),
        )
    ).all()
    show_cost = ctx.can(Permission.COST_VIEW)
    today, stale_after = today_ar(), _stale_after(db, ctx)
    current, _ = (
        current_and_upcoming(db, [o.id for o, _ in preferred_rows], today)
        if show_cost
        else ({}, {})
    )
    preferred = {
        offer.product_id: PreferredOffer(
            supplier_name=name,
            current_cost=cost_out(current[offer.id], today, stale_after)
            if offer.id in current
            else None,
        )
        for offer, name in preferred_rows
    }
    return ProductPage(
        items=[
            ProductSummary(
                id=p.id,
                name=p.name,
                category_id=p.category_id,
                category_name=category_name,
                unit_code=unit_code,
                charge_mode=p.charge_mode,
                is_active=p.is_active,
                offers_count=count,
                preferred=preferred.get(p.id),
            )
            for p, category_name, unit_code, count in page
        ],
        next_cursor=page[-1][0].name.lower() if len(rows) > limit else None,
    )


def get_product(db: AppSession, ctx: TenantContext, product_id: UUID) -> ProductOut:
    return _product_out(db, ctx, _product(db, ctx, product_id))


def create_product(db: AppSession, ctx: TenantContext, body: ProductIn) -> ProductOut:
    _category(db, ctx, body.category_id)
    _unit(db, ctx, body.unit_id)
    product = Product(
        organization_id=ctx.organization_id, **body.model_dump(include=set(_PRODUCT_FIELDS))
    )
    product.name = product.name.strip()
    db.add(product)
    _flush_unique(
        db, "uq_products_org_name", "product_name_taken", "Ya existe un producto con ese nombre"
    )
    _audit(db, ctx, "product.created", "product", product.id, after={"name": product.name})
    return _product_out(db, ctx, product)


def update_product(
    db: AppSession, ctx: TenantContext, product_id: UUID, body: ProductUpdate
) -> ProductOut:
    product = _product(db, ctx, product_id)
    fields = body.model_fields_set & set(_PRODUCT_FIELDS)
    if "category_id" in fields and body.category_id is not None:
        _category(db, ctx, body.category_id)
    if "unit_id" in fields and body.unit_id is not None:
        _unit(db, ctx, body.unit_id)
    before = _jsonable({f: getattr(product, f) for f in fields})
    for field in fields:
        value = getattr(body, field)
        if value is None and field in {
            "name",
            "category_id",
            "unit_id",
            "charge_mode",
            "is_active",
        }:
            raise AppError(422, "field_required", f"{field} no puede quedar vacío")
        setattr(product, field, value.strip() if field == "name" else value)
    _flush_unique(
        db, "uq_products_org_name", "product_name_taken", "Ya existe un producto con ese nombre"
    )
    old, new = diff(before, _jsonable({f: getattr(product, f) for f in fields}))
    if new:
        _audit(db, ctx, "product.updated", "product", product.id, before=old, after=new)
    return _product_out(db, ctx, product)


def delete_product(db: AppSession, ctx: TenantContext, product_id: UUID) -> None:
    product = _product(db, ctx, product_id)
    product.deleted_at = utcnow()
    _audit(db, ctx, "product.deleted", "product", product.id)


# --- Ofertas y costos ------------------------------------------------------------------


def _offer(db: AppSession, ctx: TenantContext, offer_id: UUID) -> SupplierProduct:
    offer = db.execute(
        select(SupplierProduct)
        .join(Product, Product.id == SupplierProduct.product_id)
        .where(
            SupplierProduct.id == offer_id,
            SupplierProduct.organization_id == ctx.organization_id,
            Product.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if offer is None:
        raise not_found()
    return offer


def _set_preferred(db: AppSession, offer: SupplierProduct) -> None:
    db.execute(
        update(SupplierProduct)
        .where(SupplierProduct.product_id == offer.product_id, SupplierProduct.id != offer.id)
        .values(is_preferred=False)
    )
    db.flush()
    offer.is_preferred = True


def _record_price(
    db: AppSession, ctx: TenantContext, offer: SupplierProduct, price: PriceIn, source: str
) -> PriceHistory:
    if not ctx.can(Permission.COSTS_EDIT):
        raise AppError(403, "permission_denied", "No tenés permiso para cargar costos")
    entry = PriceHistory(
        organization_id=ctx.organization_id,
        supplier_product_id=offer.id,
        amount=price.amount,
        amount_includes_iva=price.includes_iva,
        iva_rate=price.iva_rate,
        valid_from=price.valid_from or today_ar(),
        source=source,
        source_ref=price.source_ref,
        created_by=ctx.user_id,
    )
    db.add(entry)
    db.flush()
    _audit(
        db,
        ctx,
        "price.recorded",
        "supplier_product",
        offer.id,
        after={
            "amount": str(entry.amount),
            "includes_iva": entry.amount_includes_iva,
            "valid_from": entry.valid_from.isoformat(),
            "source": source,
        },
    )
    return entry


def create_offer(db: AppSession, ctx: TenantContext, product_id: UUID, body: OfferIn) -> ProductOut:
    product = _product(db, ctx, product_id)
    supplier = _supplier(db, ctx, body.supplier_id)
    has_offers = db.execute(
        select(func.count())
        .select_from(SupplierProduct)
        .where(SupplierProduct.product_id == product.id)
    ).scalar_one()
    offer = SupplierProduct(
        organization_id=ctx.organization_id,
        product_id=product.id,
        supplier_id=supplier.id,
        supplier_sku=body.supplier_sku,
        notes=body.notes,
    )
    db.add(offer)
    _flush_unique(
        db,
        "uq_supplier_products_organization_id_product_id_supplier_id",
        "offer_exists",
        "Ese proveedor ya ofrece este producto",
    )
    if body.is_preferred or not has_offers:  # la primera oferta es la preferida
        _set_preferred(db, offer)
    if body.cost is not None:
        _record_price(db, ctx, offer, body.cost, "MANUAL")
    _audit(
        db,
        ctx,
        "offer.created",
        "supplier_product",
        offer.id,
        after={"product": product.name, "supplier": supplier.name},
    )
    return _product_out(db, ctx, product)


def update_offer(db: AppSession, ctx: TenantContext, offer_id: UUID, body: OfferUpdate) -> OfferOut:
    offer = _offer(db, ctx, offer_id)
    for field in ("supplier_sku", "notes"):
        if field in body.model_fields_set:
            setattr(offer, field, getattr(body, field))
    if body.is_active is not None:
        offer.is_active = body.is_active
        if not body.is_active:
            offer.is_preferred = False
    if body.is_preferred:
        if not offer.is_active:
            raise AppError(409, "offer_inactive", "Una oferta inactiva no puede ser la preferida")
        _set_preferred(db, offer)
    elif body.is_preferred is False:
        offer.is_preferred = False
    db.flush()
    _audit(
        db,
        ctx,
        "offer.updated",
        "supplier_product",
        offer.id,
        after=_jsonable(body.model_dump(exclude_unset=True)),
    )
    return next(o for o in _offers_out(db, ctx, offer.product_id) if o.id == offer.id)


def list_prices(db: AppSession, ctx: TenantContext, offer_id: UUID) -> list[PriceOut]:
    offer = _offer(db, ctx, offer_id)
    rows = db.execute(
        select(PriceHistory, User.name)
        .outerjoin(User, User.id == PriceHistory.created_by)
        .where(PriceHistory.supplier_product_id == offer.id)
        .order_by(PriceHistory.valid_from.desc(), PriceHistory.created_at.desc())
    ).all()
    return [
        PriceOut(
            id=p.id,
            amount=p.amount,
            currency=p.currency,
            includes_iva=p.amount_includes_iva,
            iva_rate=p.iva_rate,
            valid_from=p.valid_from,
            source=p.source,
            source_ref=p.source_ref,
            created_by_name=name,
        )
        for p, name in rows
    ]


def record_price(db: AppSession, ctx: TenantContext, offer_id: UUID, body: PriceIn) -> OfferOut:
    offer = _offer(db, ctx, offer_id)
    _record_price(db, ctx, offer, body, "MANUAL")
    return next(o for o in _offers_out(db, ctx, offer.product_id) if o.id == offer.id)


# --- Para presupuestos -----------------------------------------------------------------------


@dataclass(frozen=True)
class LineSource:
    """Lo que una línea de presupuesto copia del catálogo al insertarse (DOMAIN_MODEL §2.6.1)."""

    product: Product
    category_name: str
    unit_code: str
    iva_rate: Decimal  # la del producto o, si no tiene, la de su categoría
    offer_id: UUID | None
    supplier_id: UUID | None
    supplier_name: str | None
    price: PriceHistory | None  # costo vigente de la oferta (None si no tiene)


def line_source(
    db: AppSession, ctx: TenantContext, product_id: UUID, offer_id: UUID | None = None
) -> LineSource:
    """El producto con la oferta indicada, o la preferida (o la única activa) si no se indica."""
    product = _product(db, ctx, product_id)
    category = ensure(db.get(Category, product.category_id), "categoría")
    unit = ensure(db.get(Unit, product.unit_id), "unidad")
    if offer_id is not None:
        offer: SupplierProduct | None = _offer(db, ctx, offer_id)
        if offer is None or offer.product_id != product.id:
            raise not_found()
    else:
        active = (
            db.execute(
                select(SupplierProduct)
                .where(
                    SupplierProduct.product_id == product.id, SupplierProduct.is_active.is_(True)
                )
                .order_by(SupplierProduct.is_preferred.desc(), SupplierProduct.created_at)
            )
            .scalars()
            .all()
        )
        offer = active[0] if active else None
    supplier = db.get(Supplier, offer.supplier_id) if offer else None
    price = current_and_upcoming(db, [offer.id], today_ar())[0].get(offer.id) if offer else None
    return LineSource(
        product=product,
        category_name=category.name,
        unit_code=unit.code,
        iva_rate=product.iva_rate if product.iva_rate is not None else category.default_iva_rate,
        offer_id=offer.id if offer else None,
        supplier_id=supplier.id if supplier else None,
        supplier_name=supplier.name if supplier else None,
        price=price,
    )


def category_info(
    db: AppSession, ctx: TenantContext, category_id: UUID
) -> tuple[Category, Decimal]:
    """Categoría (no borrada) y su IVA por defecto, para líneas libres."""
    category = _category(db, ctx, category_id)
    return category, category.default_iva_rate
