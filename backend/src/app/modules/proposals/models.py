from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin, tenant_fk, tenant_unique
from app.core.enums import check_in


class ProposalStatus(StrEnum):
    """DOMAIN_MODEL §3.3."""

    SENT = "SENT"
    VIEWED = "VIEWED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


ACTIVE = (ProposalStatus.SENT, ProposalStatus.VIEWED)
DECIDED = (ProposalStatus.ACCEPTED, ProposalStatus.REJECTED)


class ApprovalMethod(StrEnum):
    ONLINE = "ONLINE"  # el cliente desde el link
    MANUAL = "MANUAL"  # la productora, con OC u otra confirmación


class ActivityType(StrEnum):
    SENT = "SENT"
    VIEWED = "VIEWED"
    PDF_DOWNLOADED = "PDF_DOWNLOADED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


def _org_fk() -> Mapped[UUID]:
    return mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))


class Proposal(IdMixin, TimestampMixin, Base):
    __tablename__ = "proposals"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("budget_id", "budgets"),
        tenant_fk("budget_version_id", "budget_versions"),
        tenant_fk("po_document_id", "documents"),
        Index("uq_proposals_org_number", "organization_id", "number", unique=True),
        Index("uq_proposals_token_hash", "token_hash", unique=True),
        # I6: como máximo una propuesta activa por presupuesto.
        Index(
            "uq_proposals_one_active",
            "budget_id",
            unique=True,
            postgresql_where=text("status IN ('SENT', 'VIEWED')"),
        ),
        CheckConstraint(check_in("status", ProposalStatus), name="status"),
        CheckConstraint(check_in("approval_method", ApprovalMethod), name="approval_method"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    number: Mapped[int]
    budget_id: Mapped[UUID] = mapped_column(index=True)
    budget_version_id: Mapped[UUID]
    token_hash: Mapped[str] = mapped_column(String(64))  # el token nunca se guarda (§8.4)
    status: Mapped[str] = mapped_column(String(12), default=ProposalStatus.SENT.value)
    display_mode: Mapped[str] = mapped_column(String(12))
    iva_display: Mapped[str] = mapped_column(String(14))
    valid_until: Mapped[date]
    public_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_via: Mapped[str] = mapped_column(String(10), default="LINK")
    first_viewed_at: Mapped[datetime | None]
    last_viewed_at: Mapped[datetime | None]
    view_count: Mapped[int] = mapped_column(default=0, server_default="0")
    # Decisión del cliente o aprobación manual (PR 3.3)
    decided_at: Mapped[datetime | None]
    decided_by_name: Mapped[str | None] = mapped_column(String(200))
    decided_by_email: Mapped[str | None] = mapped_column(String(320))
    decision_comment: Mapped[str | None] = mapped_column(Text)
    decision_ip: Mapped[str | None] = mapped_column(String(64))
    decision_user_agent: Mapped[str | None] = mapped_column(String(500))
    approval_method: Mapped[str | None] = mapped_column(String(10))
    po_number: Mapped[str | None] = mapped_column(String(100))
    po_document_id: Mapped[UUID | None]  # la OC adjunta (PDF o foto)
    approved_by_user_id: Mapped[UUID | None]
    revoked_at: Mapped[datetime | None]
    created_by: Mapped[UUID | None]


class ProposalActivity(IdMixin, Base):
    __tablename__ = "proposal_activity"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("proposal_id", "proposals", ondelete="CASCADE"),
        CheckConstraint(check_in("type", ActivityType), name="type"),
    )

    organization_id: Mapped[UUID] = _org_fk()
    proposal_id: Mapped[UUID] = mapped_column(index=True)
    type: Mapped[str] = mapped_column(String(16))
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
