from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import Role
from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

Password = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class SwitchOrganizationRequest(BaseModel):
    organization_id: UUID


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(max_length=200)
    password: str = Password


class InvitationAccept(BaseModel):
    token: str = Field(max_length=200)
    password: str = Password
    # Obligatorio solo si el email todavía no tiene cuenta.
    name: str | None = Field(default=None, min_length=1, max_length=200)


class InvitationPreview(BaseModel):
    organization_name: str
    email: str
    role: Role
    user_exists: bool


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str


class MembershipOut(BaseModel):
    organization_id: UUID
    organization_name: str
    role: Role


class MeResponse(BaseModel):
    user: UserOut
    active_organization_id: UUID | None
    role: Role | None
    permissions: list[str]
    memberships: list[MembershipOut]
