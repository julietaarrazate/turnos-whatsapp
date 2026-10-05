from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, tenant_unique


class AuditLog(IdMixin, Base):
    """Append-only: el rol de runtime solo tiene SELECT/INSERT y un trigger bloquea cambios."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        tenant_unique(),
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        Index("ix_audit_logs_entity", "organization_id", "entity_type", "entity_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    actor_type: Mapped[str] = mapped_column(String(16))  # USER | PUBLIC_TOKEN | SYSTEM | AI
    actor_user_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[UUID | None]
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
