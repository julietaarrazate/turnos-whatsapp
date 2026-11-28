"""Dependencias de acceso. TODO endpoint bajo /api declara exactamente una de estas:

- ``Public``: sin autenticación (login, propuesta pública, ...).
- ``CurrentAuth``: usuario autenticado, con o sin organización activa.
- ``require(Permission.X)``: usuario con organización activa y ese permiso.
- ``PlatformAdmin``: la dueña de la plataforma (email en PLATFORM_ADMINS). Para cualquier otra
  persona, con o sin sesión, la ruta no existe (404).

``tests/security/test_route_access.py`` falla si alguna ruta no declara su acceso.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from app.core.config import is_platform_admin
from app.core.db import DbSession
from app.core.errors import AppError
from app.core.permissions import Permission
from app.modules.auth.service import AuthContext, ClientInfo, TenantContext, resolve_access_token
from app.modules.identity import User

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
SESSION_HINT_COOKIE = "has_session"
ACCESS_MARKER = "__access__"


def access_token_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


def client_info(request: Request) -> ClientInfo:
    return ClientInfo(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def public() -> None:
    """Marca explícita de endpoint público."""


def get_auth(request: Request, db: DbSession) -> AuthContext:
    return resolve_access_token(db, access_token_from(request))


setattr(public, ACCESS_MARKER, "public")
setattr(get_auth, ACCESS_MARKER, "authenticated")


def require(permission: Permission) -> Callable[..., TenantContext]:
    def dependency(request: Request, db: DbSession) -> TenantContext:
        auth = resolve_access_token(db, access_token_from(request))
        if auth.organization_id is None or auth.membership_id is None or auth.role is None:
            raise AppError(403, "no_active_organization", "No tenés una organización activa")
        if permission not in auth.permissions:
            raise AppError(403, "permission_denied", "No tenés permiso para esta acción")
        return TenantContext(
            user_id=auth.user_id,
            session_id=auth.session_id,
            organization_id=auth.organization_id,
            membership_id=auth.membership_id,
            role=auth.role,
            permissions=auth.permissions,
            client=client_info(request),
        )

    setattr(dependency, ACCESS_MARKER, "permission")
    dependency.__permission__ = permission  # type: ignore[attr-defined]
    dependency.__name__ = f"require_{permission.name.lower()}"
    return dependency


@dataclass(frozen=True)
class PlatformContext:
    user_id: UUID
    session_id: UUID
    client: ClientInfo


def platform_admin(request: Request, db: DbSession) -> PlatformContext:
    """Solo la dueña de la plataforma. A cualquier otra persona le responde 404, igual que una
    ruta inexistente: ni siquiera se entera de que el panel existe."""
    hidden = AppError(404, "not_found", "Not Found")  # idéntico a una ruta que no existe
    try:
        auth = resolve_access_token(db, access_token_from(request))
    except AppError:
        raise hidden from None
    user = db.get(User, auth.user_id)
    if user is None or not is_platform_admin(user.email):
        raise hidden
    return PlatformContext(user_id=user.id, session_id=auth.session_id, client=client_info(request))


setattr(platform_admin, ACCESS_MARKER, "platform")


Public = Depends(public)
CurrentAuth = Annotated[AuthContext, Depends(get_auth)]
Client = Annotated[ClientInfo, Depends(client_info)]
PlatformAdmin = Annotated[PlatformContext, Depends(platform_admin)]
