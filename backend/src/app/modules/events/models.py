from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin, tenant_fk, tenant_unique
from app.core.enums import check_in


class EventStatus(StrEnum):
    """DOMAIN_MODEL §3.1."""

    LEAD = "LEAD"
    QUOTING = "QUOTING"
    SENT = "SENT"
    NEGOTIATION = "NEGOTIATION"
    APPROVED = "APPROVED"
    IN_PRODUCTION = "IN_PRODUCTION"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    LOST = "LOST"
    CANCELLED = "CANCELLED"


def _org_fk() -> Mapped[UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))


class Event(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("client_id", "clients"),
        Index("uq_events_org_number", "organization_id", "number", unique=True),
        Index("ix_events_org_status", "organization_id", "status"),
        CheckConstraint(check_in("status", EventStatus), name="status"),
        CheckConstraint("event_days >= 1", name="event_days"),
        CheckConstraint("setup_days >= 0 AND teardown_days >= 0", name="setup_days"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="dates"
        ),
    )

    organization_id: Mapped[UUID] = _org_fk()
    number: Mapped[int]
    client_id: Mapped[UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date | None]  # None = fecha a confirmar
    end_date: Mapped[date | None]
    event_days: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    setup_days: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    teardown_days: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    venue: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(120))
    responsible_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default=EventStatus.LEAD.value)
    lost_reason: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class EventStatusChange(IdMixin, Base):
    __tablename__ = "event_status_history"
    __table_args__ = (tenant_unique(), tenant_fk("event_id", "events", ondelete="CASCADE"))

    organization_id: Mapped[UUID] = _org_fk()
    event_id: Mapped[UUID] = mapped_column(index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    changed_by: Mapped[UUID | None]
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
