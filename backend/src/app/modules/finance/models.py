from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin, tenant_fk, tenant_unique
from app.core.enums import check_in


class ExpenseCurrency(StrEnum):
    ARS = "ARS"
    USD = "USD"


def _org_fk() -> Mapped[UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))


class Expense(IdMixin, TimestampMixin, Base):
    """Un costo real del evento (DOMAIN_MODEL §2.8, D-21).

    Siempre tiene evento. Se compara con lo presupuestado por línea (``line_key`` de la versión
    aceptada) o, si no está vinculado, por categoría ("No presupuestado"): por eso pide al menos
    una de las dos. El monto efectivo se normaliza como en el motor (L1–L2): un RI computa el
    costo sin IVA; los demás, con IVA; y todo en pesos.
    """

    __tablename__ = "expenses"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("event_id", "events", ondelete="CASCADE"),
        tenant_fk("supplier_id", "suppliers"),
        tenant_fk("category_id", "categories"),
        CheckConstraint(check_in("currency", ExpenseCurrency), name="currency"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("iva_rate >= 0 AND iva_rate < 1", name="iva_rate"),
        CheckConstraint("fx_rate > 0", name="fx_rate_positive"),
        CheckConstraint("line_key IS NOT NULL OR category_id IS NOT NULL", name="line_or_category"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    event_id: Mapped[UUID] = mapped_column(index=True)
    supplier_id: Mapped[UUID | None]
    category_id: Mapped[UUID | None]
    line_key: Mapped[UUID | None]  # línea de la versión aceptada (opcional)
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))  # tal como dice el comprobante
    currency: Mapped[str] = mapped_column(String(3), default=ExpenseCurrency.ARS.value)
    amount_includes_iva: Mapped[bool] = mapped_column(Boolean, default=True)
    iva_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.21"))
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal(1))
    amount_base: Mapped[Decimal] = mapped_column(Numeric(18, 2))  # efectivo, en pesos
    expense_date: Mapped[date]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
