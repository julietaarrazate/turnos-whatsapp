from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin, tenant_fk, tenant_unique
from app.core.enums import TaxCondition, check_in
from app.domain.pricing import ChargeMode


def _org_fk() -> Mapped[UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))


class Category(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("parent_id", "categories"),
        Index(
            "uq_categories_org_name",
            "organization_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("default_iva_rate >= 0 AND default_iva_rate < 1", name="iva_rate"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[UUID | None]
    default_iva_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.21"), server_default="0.21"
    )
    sort: Mapped[int] = mapped_column(default=0, server_default="0")


class Unit(IdMixin, Base):
    __tablename__ = "units"
    __table_args__ = (tenant_unique(), UniqueConstraint("organization_id", "code"))

    organization_id: Mapped[UUID] = _org_fk()
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(60))
    allows_decimals: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Supplier(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        tenant_unique(),
        Index(
            "uq_suppliers_org_name",
            "organization_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating"),
        CheckConstraint(
            f"tax_condition IS NULL OR {check_in('tax_condition', TaxCondition)}",
            name="tax_condition",
        ),
    )

    organization_id: Mapped[UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    tax_condition: Mapped[str | None] = mapped_column(String(20))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    rating_notes: Mapped[str | None] = mapped_column(Text)
    # "Equipo propio": recursos internos (armado, personal propio). Uno por organización.
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class SupplierContact(IdMixin, TimestampMixin, Base):
    __tablename__ = "supplier_contacts"
    __table_args__ = (tenant_unique(), tenant_fk("supplier_id", "suppliers", ondelete="CASCADE"))

    organization_id: Mapped[UUID] = _org_fk()
    supplier_id: Mapped[UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class SupplierCategory(Base):
    """Rubros del proveedor."""

    __tablename__ = "supplier_categories"
    __table_args__ = (
        tenant_fk("supplier_id", "suppliers", ondelete="CASCADE"),
        tenant_fk("category_id", "categories", ondelete="CASCADE"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    supplier_id: Mapped[UUID] = mapped_column(primary_key=True)
    category_id: Mapped[UUID] = mapped_column(primary_key=True)


class Product(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("category_id", "categories"),
        tenant_fk("unit_id", "units"),
        Index(
            "uq_products_org_name",
            "organization_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(check_in("charge_mode", ChargeMode), name="charge_mode"),
        CheckConstraint("iva_rate IS NULL OR (iva_rate >= 0 AND iva_rate < 1)", name="iva_rate"),
        CheckConstraint("min_quantity IS NULL OR min_quantity > 0", name="min_quantity"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[UUID] = mapped_column(index=True)
    unit_id: Mapped[UUID]
    charge_mode: Mapped[str] = mapped_column(String(10), default=ChargeMode.FIXED.value)
    description_internal: Mapped[str | None] = mapped_column(Text)
    description_client: Mapped[str | None] = mapped_column(Text)
    min_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    iva_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class SupplierProduct(IdMixin, TimestampMixin, Base):
    """La oferta: este proveedor ofrece este producto. Como máximo una preferida por producto."""

    __tablename__ = "supplier_products"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("product_id", "products", ondelete="CASCADE"),
        tenant_fk("supplier_id", "suppliers"),
        UniqueConstraint("organization_id", "product_id", "supplier_id"),
        Index(
            "uq_supplier_products_preferred",
            "organization_id",
            "product_id",
            unique=True,
            postgresql_where=text("is_preferred"),
        ),
    )

    organization_id: Mapped[UUID] = _org_fk()
    product_id: Mapped[UUID] = mapped_column(index=True)
    supplier_id: Mapped[UUID] = mapped_column(index=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(80))
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class PriceHistory(IdMixin, Base):
    """Historial de costos APPEND-ONLY (trigger + permisos). El vigente es el de mayor
    ``valid_from`` que sea <= hoy. Se permiten fechas futuras ("desde el 1/11")."""

    __tablename__ = "price_history"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("supplier_product_id", "supplier_products", ondelete="RESTRICT"),
        Index(
            "ix_price_history_offer_valid", "organization_id", "supplier_product_id", "valid_from"
        ),
        CheckConstraint("amount >= 0", name="amount"),
        CheckConstraint("iva_rate >= 0 AND iva_rate < 1", name="iva_rate"),
        CheckConstraint(
            "source IN ('MANUAL', 'IMPORT', 'BULK_UPDATE', 'SUPPLIER_QUOTE')", name="source"
        ),
    )

    organization_id: Mapped[UUID] = _org_fk()
    supplier_product_id: Mapped[UUID]
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), default="ARS", server_default="ARS")
    amount_includes_iva: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    iva_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.21"))
    valid_from: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(20), default="MANUAL")
    source_ref: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DaysRule(StrEnum):
    """Cuántos días toma cada ítem de un paquete al insertarlo (solo importa si cobra por día)."""

    EVENT_DAYS = "EVENT_DAYS"  # los días del evento
    SETUP_DAYS = "SETUP_DAYS"  # los días de armado
    FIXED = "FIXED"  # un número fijo


class Package(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Paquete / plantilla (B-06): "Stand corporativo 6×3" = productos con cantidades."""

    __tablename__ = "packages"
    __table_args__ = (
        tenant_unique(),
        Index(
            "uq_packages_org_name",
            "organization_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    organization_id: Mapped[UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class PackageItem(IdMixin, Base):
    __tablename__ = "package_items"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("package_id", "packages", ondelete="CASCADE"),
        tenant_fk("product_id", "products"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(check_in("days_rule", DaysRule), name="days_rule"),
        CheckConstraint(
            "days_rule <> 'FIXED' OR (fixed_days IS NOT NULL AND fixed_days >= 1)",
            name="fixed_days",
        ),
    )

    organization_id: Mapped[UUID] = _org_fk()
    package_id: Mapped[UUID] = mapped_column(index=True)
    product_id: Mapped[UUID]
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    days_rule: Mapped[str] = mapped_column(String(12), default=DaysRule.EVENT_DAYS.value)
    fixed_days: Mapped[int | None] = mapped_column(SmallInteger)
    section_title: Mapped[str | None] = mapped_column(String(200))  # vacío: la sección elegida
    description_client_override: Mapped[str | None] = mapped_column(Text)
    sort: Mapped[int] = mapped_column(default=0)
