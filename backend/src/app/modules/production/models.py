from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin, tenant_fk, tenant_unique
from app.core.enums import check_in


class HireStatus(StrEnum):
    """Lista de contratación, como la sigue la piloto en su planilla: cotizado → confirmado →
    factura cargada → pagado (siempre hacia adelante) · cancelado antes de facturar."""

    TO_HIRE = "TO_HIRE"  # cotizado / a contratar
    CONFIRMED = "CONFIRMED"
    INVOICED = "INVOICED"  # factura cargada
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


def _org_fk() -> Mapped[UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))


class EventSupplier(IdMixin, TimestampMixin, Base):
    """La lista de contratación: un renglón por proveedor de la versión aceptada."""

    __tablename__ = "event_suppliers"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("event_id", "events", ondelete="CASCADE"),
        tenant_fk("supplier_id", "suppliers"),
        CheckConstraint(check_in("status", HireStatus), name="status"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    event_id: Mapped[UUID] = mapped_column(index=True)
    supplier_id: Mapped[UUID | None]  # None: ítems sin proveedor (propios o libres)
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default=HireStatus.TO_HIRE.value)
    # Guardado al iniciar producción: la suma de costos de sus líneas en la baseline.
    budgeted_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    # Snapshot de las líneas (la baseline está congelada, así que no cambia).
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    invoice_number: Mapped[str | None] = mapped_column(String(50))  # Nº de factura del proveedor
    payment_terms: Mapped[str | None] = mapped_column(String(200))  # condición de pago
    confirmed_at: Mapped[datetime | None]
    paid_at: Mapped[datetime | None]
    sort: Mapped[int] = mapped_column(default=0)


class ProductionTask(IdMixin, TimestampMixin, Base):
    __tablename__ = "production_tasks"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("event_id", "events", ondelete="CASCADE"),
        tenant_fk("category_id", "categories"),
        CheckConstraint(check_in("status", TaskStatus), name="status"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    event_id: Mapped[UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default=TaskStatus.TODO.value)
    assignee_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None]
    category_id: Mapped[UUID | None]
    line_key: Mapped[UUID | None]
    sort: Mapped[int] = mapped_column(default=0)


class PieceArea(StrEnum):
    """Área de fabricación de una pieza (filtro del tablero)."""

    CARPENTRY = "CARPENTRY"  # carpintería
    METAL = "METAL"  # herrería
    GRAPHICS = "GRAPHICS"  # gráfica, corpóreos, pantallas
    OTHER = "OTHER"


class PieceStatus(StrEnum):
    """Fases de una pieza a medida. Se puede ir y volver (un plano rechazado vuelve a diseño)."""

    DESIGN = "DESIGN"  # pendiente diseño
    TO_BUY = "TO_BUY"  # aprobado / a comprar
    IN_WORKSHOP = "IN_WORKSHOP"
    READY = "READY"  # listo para carga
    MOUNTED = "MOUNTED"  # en predio / montado


class EventPiece(IdMixin, TimestampMixin, Base):
    """Una pieza que se fabrica para el evento (mostrador, corpóreo, tarima…)."""

    __tablename__ = "event_pieces"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("event_id", "events", ondelete="CASCADE"),
        CheckConstraint(check_in("area", PieceArea), name="area"),
        CheckConstraint(check_in("status", PieceStatus), name="status"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    event_id: Mapped[UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(10), default=PieceArea.OTHER.value)
    status: Mapped[str] = mapped_column(String(12), default=PieceStatus.DESIGN.value)
    assignee_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime | None]
    sort: Mapped[int] = mapped_column(default=0)


class PieceProgress(IdMixin, Base):
    """Un avance de una pieza: foto y/o nota de quien la está haciendo. Inmutable (como una
    bitácora): no se edita; si algo estuvo mal se sube otro avance."""

    __tablename__ = "piece_updates"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("piece_id", "event_pieces", ondelete="CASCADE"),
        tenant_fk("event_id", "events", ondelete="CASCADE"),
        tenant_fk("photo_document_id", "documents"),
        CheckConstraint("note IS NOT NULL OR photo_document_id IS NOT NULL", name="has_content"),
        Index("ix_piece_updates_piece_created", "piece_id", "created_at"),
        Index("ix_piece_updates_event_created", "event_id", "created_at"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    event_id: Mapped[UUID]
    piece_id: Mapped[UUID]
    author_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    photo_document_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
