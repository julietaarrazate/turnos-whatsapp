from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin, tenant_unique
from app.core.enums import Role, TaxCondition, check_in


class MembershipStatus(StrEnum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


FOLLOW_UP_DAYS = "follow_up_days"
DEFAULT_FOLLOW_UP_DAYS = 5  # PRODUCT_SPEC §8: "para seguir" tras N días sin decisión


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(check_in("tax_condition", TaxCondition), name="tax_condition"),
    )

    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    tax_condition: Mapped[str] = mapped_column(String(20), default=TaxCondition.RI.value)
    base_currency: Mapped[str] = mapped_column(String(3), default="ARS", server_default="ARS")
    timezone: Mapped[str] = mapped_column(
        String(64),
        default="America/Argentina/Buenos_Aires",
        server_default="America/Argentina/Buenos_Aires",
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # Pausada desde el panel de la plataforma: nadie de la organización puede usarla.
    suspended_at: Mapped[datetime | None]
    # Creada desde "Crear cuenta": nadie la usa hasta que la dueña de la plataforma la aprueba.
    pending_approval: Mapped[bool] = mapped_column(default=False, server_default="false")

    @property
    def usable(self) -> bool:
        return self.suspended_at is None and not self.pending_approval

    @property
    def follow_up_days(self) -> int:
        value = self.settings.get(FOLLOW_UP_DAYS)
        return value if isinstance(value, int) and value > 0 else DEFAULT_FOLLOW_UP_DAYS


class Membership(IdMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        tenant_unique(),
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint(check_in("role", Role), name="role"),
        CheckConstraint(check_in("status", MembershipStatus), name="status"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=MembershipStatus.ACTIVE.value)
