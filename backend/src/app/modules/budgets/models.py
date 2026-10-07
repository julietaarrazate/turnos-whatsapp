from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin, tenant_fk, tenant_unique
from app.core.enums import check_in
from app.domain.pricing import ChargeMode, LinePricingMode, VersionPricingMode

MONEY = Numeric(18, 2)
UNIT = Numeric(18, 6)
RATE = Numeric(14, 6)  # markups y márgenes pueden ser grandes o negativos


class ClientPriceLabel(StrEnum):
    """Lo que ve el cliente en lugar del importe de la línea (planilla de la piloto)."""

    BONIFICADO = "BONIFICADO"  # incluido sin cargo
    A_DEFINIR = "A_DEFINIR"  # todavía sin precio


class VersionStatus(StrEnum):
    DRAFT = "DRAFT"
    FROZEN = "FROZEN"


class BudgetCurrency(StrEnum):
    ARS = "ARS"
    USD = "USD"


def _org_fk() -> Mapped[UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))


class Budget(IdMixin, TimestampMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("event_id", "events"),
        Index("uq_budgets_org_number", "organization_id", "number", unique=True),
        CheckConstraint(check_in("currency", BudgetCurrency), name="currency"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    number: Mapped[int]
    event_id: Mapped[UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3), default=BudgetCurrency.ARS.value)
    created_by: Mapped[UUID | None]


class BudgetVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "budget_versions"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("budget_id", "budgets", ondelete="CASCADE"),
        tenant_fk("cloned_from_version_id", "budget_versions"),
        UniqueConstraint("budget_id", "version_no"),
        # I4: como máximo un borrador por presupuesto.
        Index(
            "uq_budget_versions_one_draft",
            "budget_id",
            unique=True,
            postgresql_where=text("status = 'DRAFT'"),
        ),
        CheckConstraint(check_in("status", VersionStatus), name="status"),
        CheckConstraint(check_in("pricing_mode", VersionPricingMode), name="pricing_mode"),
        CheckConstraint("global_discount_rate >= 0 AND global_discount_rate < 1", name="discount"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    budget_id: Mapped[UUID] = mapped_column(index=True)
    version_no: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(10), default=VersionStatus.DRAFT.value)
    lock_version: Mapped[int] = mapped_column(default=0, server_default="0")

    # Inputs de la versión (§5.5)
    pricing_mode: Mapped[str] = mapped_column(String(10), default=VersionPricingMode.LINE.value)
    markup_override: Mapped[Decimal | None] = mapped_column(RATE)
    target_margin: Mapped[Decimal | None] = mapped_column(RATE)
    target_price: Mapped[Decimal | None] = mapped_column(MONEY)
    target_includes_iva: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    global_discount_rate: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), default=Decimal(0), server_default="0"
    )

    # Snapshots: el contexto con el que se calcula (no cambia si cambian las reglas).
    fx_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    header_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Outputs del motor (§5.4)
    cost_direct: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    sale_subtotal: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    global_discount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    sale_net: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    sale_charges: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    sale_charges_detail: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    profit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    markup: Mapped[Decimal | None] = mapped_column(RATE)
    margin_gross: Mapped[Decimal | None] = mapped_column(RATE)
    margin_net: Mapped[Decimal | None] = mapped_column(RATE)
    iva: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0), server_default="0")
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Importes que ve el cliente en la moneda de presentación (USD), si no es la base.
    presentation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pricing_engine_version: Mapped[str] = mapped_column(String(20))
    snapshot_schema_version: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1"
    )

    change_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID | None]
    frozen_at: Mapped[datetime | None]
    frozen_by: Mapped[UUID | None]
    cloned_from_version_id: Mapped[UUID | None]


class BudgetSection(IdMixin, Base):
    __tablename__ = "budget_sections"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("version_id", "budget_versions", ondelete="CASCADE"),
        UniqueConstraint("version_id", "section_key"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    version_id: Mapped[UUID] = mapped_column(index=True)
    section_key: Mapped[UUID]  # estable entre versiones
    title_client: Mapped[str] = mapped_column(String(200))
    sort: Mapped[int] = mapped_column(default=0)


class BudgetLine(IdMixin, Base):
    """La línea con snapshot completo (DOMAIN_MODEL §2.6.1): se puede recalcular y leer
    aunque el producto, el proveedor o la categoría cambien o se borren."""

    __tablename__ = "budget_lines"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("version_id", "budget_versions", ondelete="CASCADE"),
        tenant_fk("section_id", "budget_sections", ondelete="CASCADE"),
        tenant_fk("product_id", "products"),
        tenant_fk("supplier_product_id", "supplier_products"),
        tenant_fk("supplier_id", "suppliers"),
        tenant_fk("price_history_id", "price_history"),
        tenant_fk("category_id", "categories"),
        UniqueConstraint("version_id", "line_key"),
        CheckConstraint(check_in("charge_mode", ChargeMode), name="charge_mode"),
        CheckConstraint(check_in("pricing_mode", LinePricingMode), name="pricing_mode"),
        CheckConstraint("quantity > 0", name="quantity"),  # I10
        CheckConstraint("days >= 1", name="days"),
        CheckConstraint("unit_cost_amount >= 0", name="unit_cost"),
        CheckConstraint("discount_rate >= 0 AND discount_rate < 1", name="discount"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    version_id: Mapped[UUID] = mapped_column(index=True)
    section_id: Mapped[UUID] = mapped_column(index=True)
    line_key: Mapped[UUID]  # estable entre versiones (para comparar)
    sort: Mapped[int] = mapped_column(default=0)

    # Referencias (trazabilidad; todas opcionales: hay líneas libres)
    product_id: Mapped[UUID | None]
    supplier_product_id: Mapped[UUID | None]
    supplier_id: Mapped[UUID | None]
    price_history_id: Mapped[UUID | None]
    category_id: Mapped[UUID | None]

    # Snapshot descriptivo
    name_internal: Mapped[str] = mapped_column(String(200))
    description_client: Mapped[str | None] = mapped_column(Text)
    category_name: Mapped[str | None] = mapped_column(String(120))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    unit_code: Mapped[str] = mapped_column(String(16), default="u")
    charge_mode: Mapped[str] = mapped_column(String(10), default=ChargeMode.FIXED.value)
    iva_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.21"))
    notes_internal: Mapped[str | None] = mapped_column(Text)
    show_on_proposal: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    client_price_label: Mapped[str | None] = mapped_column(String(12))

    # Inputs
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    days: Mapped[int] = mapped_column(SmallInteger, default=1)
    unit_cost_amount: Mapped[Decimal] = mapped_column(UNIT)
    unit_cost_currency: Mapped[str] = mapped_column(String(3), default="ARS")
    unit_cost_includes_iva: Mapped[bool] = mapped_column(Boolean, default=False)
    unit_cost_iva_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.21"))
    # El proveedor cotizó la línea entera: unit_cost_amount es el total (no × cantidad × días).
    cost_is_total: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    cost_as_of: Mapped[date | None]
    pricing_mode: Mapped[str] = mapped_column(String(10), default=LinePricingMode.MARKUP.value)
    markup_manual: Mapped[Decimal | None] = mapped_column(RATE)
    target_margin: Mapped[Decimal | None] = mapped_column(RATE)
    target_price: Mapped[Decimal | None] = mapped_column(MONEY)
    discount_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal(0))
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Markup resuelto con las reglas al insertar (§5.3)
    rule_markup: Mapped[Decimal] = mapped_column(RATE)
    rule_source: Mapped[str] = mapped_column(String(15))
    rule_source_id: Mapped[str | None] = mapped_column(String(64))

    # Outputs del motor
    unit_cost_effective: Mapped[Decimal] = mapped_column(UNIT, default=Decimal(0))
    fx_rate: Mapped[Decimal] = mapped_column(UNIT, default=Decimal(1))
    cost_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    markup_applied: Mapped[Decimal | None] = mapped_column(RATE)
    markup_source: Mapped[str | None] = mapped_column(String(15))
    markup_source_id: Mapped[str | None] = mapped_column(String(64))
    sale_list_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    sale_total: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    profit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
    margin: Mapped[Decimal | None] = mapped_column(RATE)
    allocated_global_discount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal(0))
