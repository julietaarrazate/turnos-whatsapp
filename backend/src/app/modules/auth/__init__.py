"""Autenticación: sesiones, refresh rotativo, invitaciones, permisos y reset de contraseña."""

from app.modules.auth.dependencies import (
    Client,
    CurrentAuth,
    PlatformAdmin,
    PlatformContext,
    Public,
    require,
)
from app.modules.auth.models import AuthSession, Invitation
from app.modules.auth.router import router, start_session
from app.modules.auth.schemas import MeResponse, Password
from app.modules.auth.service import (
    AuthContext,
    ClientInfo,
    TenantContext,
    create_invitation,
    find_user_by_email,
)

__all__ = [
    "AuthContext",
    "AuthSession",
    "Client",
    "ClientInfo",
    "CurrentAuth",
    "Invitation",
    "MeResponse",
    "Password",
    "PlatformAdmin",
    "PlatformContext",
    "Public",
    "TenantContext",
    "create_invitation",
    "find_user_by_email",
    "require",
    "router",
    "start_session",
]
