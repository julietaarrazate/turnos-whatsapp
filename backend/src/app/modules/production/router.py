from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.production import service
from app.modules.production.schemas import (
    EventSupplierOut,
    EventSupplierUpdate,
    ProductionOut,
    TaskIn,
    TaskOut,
    TaskUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["production"])

View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Manage = Annotated[TenantContext, Depends(require(Permission.PRODUCTION_MANAGE))]


@router.post("/events/{event_id}/start-production")
def start_production(event_id: UUID, ctx: Manage, db: DbSession) -> ProductionOut:
    """Iniciar producción (APPROVED → IN_PRODUCTION): arma la lista de contratación por
    proveedor desde la versión aceptada y las tareas sugeridas."""
    return service.start(db, ctx, event_id)


@router.get("/events/{event_id}/production")
def get_production(event_id: UUID, ctx: View, db: DbSession) -> ProductionOut:
    return service.production(db, ctx, event_id)


@router.patch("/event-suppliers/{event_supplier_id}")
def update_supplier(
    event_supplier_id: UUID, body: EventSupplierUpdate, ctx: Manage, db: DbSession
) -> EventSupplierOut:
    """Marcar un proveedor como confirmado o cancelado, o anotar algo."""
    return service.update_supplier(db, ctx, event_supplier_id, body)


@router.post("/events/{event_id}/tasks", status_code=status.HTTP_201_CREATED)
def add_task(event_id: UUID, body: TaskIn, ctx: Manage, db: DbSession) -> TaskOut:
    return service.add_task(db, ctx, event_id, body)


@router.patch("/tasks/{task_id}")
def update_task(task_id: UUID, body: TaskUpdate, ctx: Manage, db: DbSession) -> TaskOut:
    return service.update_task(db, ctx, task_id, body)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: UUID, ctx: Manage, db: DbSession) -> None:
    service.delete_task(db, ctx, task_id)
