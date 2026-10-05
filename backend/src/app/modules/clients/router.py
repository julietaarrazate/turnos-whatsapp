from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.clients import service
from app.modules.clients.schemas import ClientIn, ClientOut, ClientPage, ClientUpdate

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Edit = Annotated[TenantContext, Depends(require(Permission.CLIENTS_EDIT))]


@router.get("")
def list_clients(
    ctx: View,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ClientPage:
    return service.list_clients(db, ctx, q, cursor, limit)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(body: ClientIn, ctx: Edit, db: DbSession) -> ClientOut:
    return service.create_client(db, ctx, body)


@router.get("/{client_id}")
def get_client(client_id: UUID, ctx: View, db: DbSession) -> ClientOut:
    return service.get_client(db, ctx, client_id)


@router.patch("/{client_id}")
def update_client(client_id: UUID, body: ClientUpdate, ctx: Edit, db: DbSession) -> ClientOut:
    return service.update_client(db, ctx, client_id, body)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: UUID, ctx: Edit, db: DbSession) -> None:
    service.delete_client(db, ctx, client_id)
