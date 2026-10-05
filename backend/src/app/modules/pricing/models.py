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
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin, tenant_unique
from app.core.enums import check_in
from app.domain.pricing import RuleMode


def _org_fk() -> Mapped[UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))


class MarkupScope(StrEnum):
    ORG = "ORG"
    CATEGORY = "CATEGORY"
    PRODUCT = "PRODUCT"
    CLIENT = "CLIENT"


class MarkupRuleRow(IdMixin, TimestampMixin, Base):
    """Regla de markup o margen (DOMAIN_MODEL §2.4). `scope_id` apunta a una categoría, un
    producto o un cliente según `scope`; es polimórfico, así que lo valida el servicio."""

    __tablename__ = "markup_rules"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint(
            "organization_id",
            "scope",
            "scope_id",
            name="uq_markup_rules_scope",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(check_in("scope", MarkupScope), name="scope"),
        CheckConstraint("(scope = 'ORG') = (scope_id IS NULL)", name="scope_id"),
        CheckConstraint(check_in("mode", RuleMode), name="mode"),
        CheckConstraint(
            "(mode = 'MARKUP' AND value >= 0 AND value <= 100) "
            "OR (mode = 'MARGIN' AND value >= 0 AND value < 1)",
            name="value",
        ),
    )

    organization_id: Mapped[UUID] = _org_fk()
    scope: Mapped[str] = mapped_column(String(10))
    scope_id: Mapped[UUID | None]
    mode: Mapped[str] = mapped_column(String(10), default=RuleMode.MARKUP.value)
    value: Mapped[Decimal] = mapped_column(Numeric(9, 6))


class SaleChargeRow(IdMixin, TimestampMixin, Base):
    """Costo proporcional a la venta neta: IIBB, impuesto al cheque, comisiones."""

    __tablename__ = "sale_charges"
    __table_args__ = (
        tenant_unique(),
        Index("uq_sale_charges_org_name", "organization_id", text("lower(name)"), unique=True),
        CheckConstraint("rate >= 0 AND rate < 1", name="rate"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(80))
    rate: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    applies_by_default: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    sort: Mapped[int] = mapped_column(default=0, server_default="0")


class FxRate(IdMixin, Base):
    """Historial de tipos de cambio (append-only). El último es el valor por defecto."""

    __tablename__ = "fx_rates"
    __table_args__ = (
        tenant_unique(),
        Index("ix_fx_rates_latest", "organization_id", "currency", "rate_date"),
        CheckConstraint("currency IN ('USD')", name="currency"),
        CheckConstraint("rate > 0", name="rate"),
        CheckConstraint("source IN ('MANUAL')", name="source"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))  # ARS por unidad
    rate_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(10), default="MANUAL")
    created_by: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
