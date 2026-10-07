"""Paquetes / plantillas (B-06): una lista de productos con cantidad, regla de días y sección.

Insertar un paquete en un presupuesto crea líneas editables (lo hace el módulo de
presupuestos con `package_spec`): con los costos vigentes y los markups resueltos, como si se
agregaran a mano.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select

from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.core.security import utcnow
from app.domain.pricing import ChargeMode
from app.modules.auth import TenantContext
from app.modules.catalog.models import DaysRule, Package, PackageItem, Product, Unit
from app.modules.catalog.schemas import (
    PackageIn,
    PackageItemOut,
    PackageOut,
    PackageSummary,
)
from app.modules.catalog.service import _audit, _flush_unique, _product


def _package(db: AppSession, ctx: TenantContext, package_id: UUID) -> Package:
    package = db.execute(
        select(Package).where(
            Package.id == package_id,
            Package.organization_id == ctx.organization_id,
            Package.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if package is None:
        raise not_found()
    return package


def _items(db: AppSession, package_id: UUID) -> list[tuple[PackageItem, Product, Unit]]:
    return list(
        db.execute(
            select(PackageItem, Product, Unit)
            .join(Product, Product.id == PackageItem.product_id)
            .join(Unit, Unit.id == Product.unit_id)
            .where(PackageItem.package_id == package_id)
            .order_by(PackageItem.sort)
        ).all()
    )


def _out(db: AppSession, package: Package) -> PackageOut:
    return PackageOut(
        id=package.id,
        name=package.name,
        description=package.description,
        is_active=package.is_active,
        items=[
            PackageItemOut(
                id=item.id,
                product_id=product.id,
                product_name=product.name,
                unit_code=unit.code,
                charge_mode=ChargeMode(product.charge_mode),
                quantity=item.quantity,
                days_rule=item.days_rule,
                fixed_days=item.fixed_days,
                section_title=item.section_title,
                description_client_override=item.description_client_override,
            )
            for item, product, unit in _items(db, package.id)
        ],
    )


def list_packages(db: AppSession, ctx: TenantContext, q: str | None) -> list[PackageSummary]:
    counts = (
        select(PackageItem.package_id, func.count().label("n"))
        .group_by(PackageItem.package_id)
        .subquery()
    )
    query = (
        select(Package, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.package_id == Package.id)
        .where(Package.organization_id == ctx.organization_id, Package.deleted_at.is_(None))
        .order_by(Package.name)
    )
    if q and q.strip():
        query = query.where(Package.name.ilike(f"%{q.strip()}%"))
    return [
        PackageSummary(
            id=p.id, name=p.name, description=p.description, is_active=p.is_active, item_count=n
        )
        for p, n in db.execute(query).all()
    ]


def get_package(db: AppSession, ctx: TenantContext, package_id: UUID) -> PackageOut:
    return _out(db, _package(db, ctx, package_id))


def _replace_items(db: AppSession, ctx: TenantContext, package: Package, body: PackageIn) -> None:
    db.execute(delete(PackageItem).where(PackageItem.package_id == package.id))
    for sort, item in enumerate(body.items):
        _product(db, ctx, item.product_id)  # 404 si no existe o es de otra organización
        db.add(
            PackageItem(
                organization_id=ctx.organization_id,
                package_id=package.id,
                product_id=item.product_id,
                quantity=item.quantity,
                days_rule=item.days_rule,
                fixed_days=item.fixed_days if item.days_rule == DaysRule.FIXED else None,
                section_title=(item.section_title or "").strip() or None,
                description_client_override=item.description_client_override,
                sort=sort,
            )
        )
    db.flush()


def _flush_name(db: AppSession) -> None:
    _flush_unique(
        db, "uq_packages_org_name", "package_name_taken", "Ya existe un paquete con ese nombre"
    )


def create_package(db: AppSession, ctx: TenantContext, body: PackageIn) -> PackageOut:
    package = Package(
        organization_id=ctx.organization_id,
        name=body.name.strip(),
        description=body.description,
        is_active=body.is_active,
    )
    db.add(package)
    _flush_name(db)
    _replace_items(db, ctx, package, body)
    _audit(
        db,
        ctx,
        "package.created",
        "package",
        package.id,
        after={"name": package.name, "items": len(body.items)},
    )
    return _out(db, package)


def update_package(
    db: AppSession, ctx: TenantContext, package_id: UUID, body: PackageIn
) -> PackageOut:
    """Reemplaza el paquete completo (nombre, descripción e ítems): es una plantilla."""
    package = _package(db, ctx, package_id)
    package.name = body.name.strip()
    package.description = body.description
    package.is_active = body.is_active
    _flush_name(db)
    _replace_items(db, ctx, package, body)
    _audit(
        db,
        ctx,
        "package.updated",
        "package",
        package.id,
        after={"name": package.name, "items": len(body.items)},
    )
    return _out(db, package)


def delete_package(db: AppSession, ctx: TenantContext, package_id: UUID) -> None:
    package = _package(db, ctx, package_id)
    package.deleted_at = utcnow()
    _audit(db, ctx, "package.deleted", "package", package.id, before={"name": package.name})


@dataclass(frozen=True)
class PackageLine:
    """Un ítem del paquete listo para insertar como línea."""

    product_id: UUID
    quantity: Decimal
    days: int | None  # None: lo decide el producto (cobro fijo) o el evento
    section_title: str | None
    description_client: str | None


def package_spec(
    db: AppSession,
    ctx: TenantContext,
    package_id: UUID,
    *,
    event_days: int,
    setup_days: int,
) -> tuple[str, list[PackageLine]]:
    """Nombre y líneas del paquete, con los días ya resueltos según la regla de cada ítem."""
    package = _package(db, ctx, package_id)
    if not package.is_active:
        raise AppError(409, "package_inactive", "El paquete está desactivado")
    lines = []
    for item, product, _ in _items(db, package.id):
        if product.deleted_at is not None:
            continue  # el producto se borró del catálogo después de armar el paquete
        rule = DaysRule(item.days_rule)
        days = {
            DaysRule.EVENT_DAYS: event_days,
            DaysRule.SETUP_DAYS: max(setup_days, 1),
            DaysRule.FIXED: item.fixed_days or 1,
        }[rule]
        lines.append(
            PackageLine(
                product_id=product.id,
                quantity=item.quantity,
                days=days,
                section_title=item.section_title,
                description_client=item.description_client_override,
            )
        )
    if not lines:
        raise AppError(409, "package_empty", "El paquete no tiene productos activos")
    return package.name, lines
