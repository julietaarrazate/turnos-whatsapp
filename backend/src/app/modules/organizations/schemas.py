from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import Role, TaxCondition
from app.modules.identity import MembershipStatus


class OrganizationOut(BaseModel):
    id: UUID
    name: str
    legal_name: str | None
    tax_id: str | None
    tax_condition: TaxCondition
    base_currency: str
    timezone: str
    viewer_sees_financials: bool
    follow_up_days: int  # "para seguir": días sin decisión desde el envío


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    viewer_sees_financials: bool | None = None
    follow_up_days: int | None = Field(default=None, ge=1, le=60)


class OrganizationFiscalUpdate(BaseModel):
    legal_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, pattern=r"^\d{2}-?\d{8}-?\d$")
    tax_condition: TaxCondition | None = None


class MemberOut(BaseModel):
    membership_id: UUID
    user_id: UUID
    name: str
    # Solo se emite a quien puede administrar miembros (redacción en el servidor).
    email: str | None
    role: Role
    status: MembershipStatus


class MemberUpdate(BaseModel):
    role: Role | None = None
    status: MembershipStatus | None = None


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role


class InvitationOut(BaseModel):
    id: UUID
    email: str
    role: Role
    created_at: datetime
    expires_at: datetime


class AuditLogOut(BaseModel):
    id: UUID
    action: str
    entity_type: str
    entity_id: UUID | None
    actor_type: str
    actor_user_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    next_cursor: UUID | None
