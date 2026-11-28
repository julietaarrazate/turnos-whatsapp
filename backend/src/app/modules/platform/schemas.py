from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.modules.auth import Password


class OrgMemberOut(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: str
    status: str


class PlatformOrgOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    suspended_at: datetime | None
    pending_approval: bool
    members: list[OrgMemberOut]
    events: int
    budgets: int
    last_activity_at: datetime | None


class UserOrgOut(BaseModel):
    organization_id: UUID
    organization_name: str
    role: str
    status: str


class PlatformUserOut(BaseModel):
    id: UUID
    name: str
    email: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    last_seen_at: datetime | None  # último uso de cualquiera de sus sesiones
    open_sessions: int
    organizations: list[UserOrgOut]
    is_me: bool


class PlatformSessionOut(BaseModel):
    id: UUID
    user_id: UUID
    user_name: str
    organization_name: str | None
    created_at: datetime
    last_used_at: datetime
    ip: str | None
    user_agent: str | None
    is_current: bool


class PlatformActivityOut(BaseModel):
    created_at: datetime
    organization_name: str
    user_name: str | None
    actor_type: str
    action: str
    entity_type: str


class PlatformOverview(BaseModel):
    organizations: list[PlatformOrgOut]
    users: list[PlatformUserOut]
    sessions: list[PlatformSessionOut]
    activity: list[PlatformActivityOut]


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=320)
    password: str = Password
    # Campo trampa: invisible para las personas; los robots que llenan todo lo completan.
    website: str = Field(default="", max_length=200)
