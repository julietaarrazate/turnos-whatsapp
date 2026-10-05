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
