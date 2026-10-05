"""Dependencias de acceso. TODO endpoint bajo /api declara exactamente una de estas:

- ``Public``: sin autenticación (login, propuesta pública, ...).
- ``CurrentAuth``: usuario autenticado, con o sin organización activa.
- ``require(Permission.X)``: usuario con organización activa y ese permiso.

``tests/security/test_route_access.py`` falla si alguna ruta no declara su acceso.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.core.db import DbSession
from app.core.errors import AppError
from app.core.permissions import Permission
from app.modules.auth.service import AuthContext, ClientInfo, TenantContext, resolve_access_token

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
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


Public = Depends(public)
CurrentAuth = Annotated[AuthContext, Depends(get_auth)]
Client = Annotated[ClientInfo, Depends(client_info)]
