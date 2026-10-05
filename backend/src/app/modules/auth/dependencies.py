from typing import Annotated

from fastapi import Depends, Request

from app.core.db import DbSession
from app.modules.auth.service import AuthContext, ClientInfo, resolve_access_token

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


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


def get_auth(request: Request, db: DbSession) -> AuthContext:
    """Usuario autenticado (con o sin organización activa)."""
    return resolve_access_token(db, access_token_from(request))


CurrentAuth = Annotated[AuthContext, Depends(get_auth)]
Client = Annotated[ClientInfo, Depends(client_info)]
