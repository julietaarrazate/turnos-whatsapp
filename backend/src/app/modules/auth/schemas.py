from datetime import datetime
from typing import Any
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
    uploads_enabled: bool  # hay dónde guardar archivos (comprobantes, OC)
    pin_enabled: bool = False  # bloqueo de pantalla con PIN activado


class PasskeyCredential(BaseModel):
    """Lo que devuelve el navegador (``PublicKeyCredential.toJSON()``); lo valida la librería."""

    credential: dict[str, Any]


class PasskeyOut(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Password


class PinIn(BaseModel):
    pin: str = Field(min_length=4, max_length=4)


class PinCheckOut(BaseModel):
    ok: bool
    attempts_left: int  # 0 = se cerró la sesión: hay que volver a entrar
