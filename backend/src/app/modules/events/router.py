from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.events import service
from app.modules.events.models import EventStatus
from app.modules.events.schemas import EventIn, EventOut, EventPage, EventUpdate, StatusChangeIn

router = APIRouter(prefix="/api/v1/events", tags=["events"])

View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Edit = Annotated[TenantContext, Depends(require(Permission.BUDGET_EDIT))]
# Marcar perdido, cancelar y reabrir (PRODUCT_SPEC §9: "Aprobar manualmente / marcar perdido").
Decide = Annotated[TenantContext, Depends(require(Permission.PROPOSAL_DECIDE))]


@router.get("")
def list_events(
    ctx: View,
    db: DbSession,
    *,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_in: Annotated[list[EventStatus] | None, Query(alias="status")] = None,
    client_id: UUID | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EventPage:
    return service.list_events(
        db, ctx, q=q, status=status_in, client_id=client_id, cursor=cursor, limit=limit
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_event(body: EventIn, ctx: Edit, db: DbSession) -> EventOut:
    return service.event_out(db, ctx, service.create_event(db, ctx, body))


@router.get("/{event_id}")
def get_event(event_id: UUID, ctx: View, db: DbSession) -> EventOut:
    return service.event_out(db, ctx, service.get_event(db, ctx, event_id))


@router.patch("/{event_id}")
def update_event(event_id: UUID, body: EventUpdate, ctx: Edit, db: DbSession) -> EventOut:
    return service.update_event(db, ctx, event_id, body)


@router.post("/{event_id}/status")
def change_status(event_id: UUID, body: StatusChangeIn, ctx: Decide, db: DbSession) -> EventOut:
    """Marcar perdido, cancelar o reabrir. Los demás cambios de estado son automáticos."""
    return service.change_status(db, ctx, event_id, body)
