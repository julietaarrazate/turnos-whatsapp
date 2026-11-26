from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.production import my_work, pieces, service, updates
from app.modules.production.schemas import (
    EventSupplierOut,
    EventSupplierUpdate,
    MyPieceUpdate,
    MyTaskUpdate,
    MyWorkOut,
    PieceIn,
    PieceOut,
    PiecesOut,
    PieceUpdate,
    PieceUpdateIn,
    PieceUpdateOut,
    ProductionOut,
    TaskIn,
    TaskOut,
    TaskUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["production"])

View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Manage = Annotated[TenantContext, Depends(require(Permission.PRODUCTION_MANAGE))]
OwnWork = Annotated[TenantContext, Depends(require(Permission.WORK_OWN))]


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


@router.get("/events/{event_id}/pieces")
def list_pieces(event_id: UUID, ctx: View, db: DbSession) -> PiecesOut:
    """Las piezas a medida del evento y su avance (% promedio de fases, cuántas listas)."""
    return pieces.list_pieces(db, ctx, event_id)


@router.post("/events/{event_id}/pieces", status_code=status.HTTP_201_CREATED)
def add_piece(event_id: UUID, body: PieceIn, ctx: Manage, db: DbSession) -> PieceOut:
    return pieces.add_piece(db, ctx, event_id, body)


@router.patch("/pieces/{piece_id}")
def update_piece(piece_id: UUID, body: PieceUpdate, ctx: Manage, db: DbSession) -> PieceOut:
    """Cambiar la fase (diseño → a comprar → taller → listo → montado, o volver), el responsable…"""
    return pieces.update_piece(db, ctx, piece_id, body)


@router.delete("/pieces/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_piece(piece_id: UUID, ctx: Manage, db: DbSession) -> None:
    pieces.delete_piece(db, ctx, piece_id)


@router.get("/my-work")
def get_my_work(ctx: OwnWork, db: DbSession) -> MyWorkOut:
    """Mis tareas: piezas y tareas asignadas a quien consulta, pendientes, en eventos abiertos."""
    return my_work.my_work(db, ctx)


@router.patch("/my-work/pieces/{piece_id}")
def move_my_piece(piece_id: UUID, body: MyPieceUpdate, ctx: OwnWork, db: DbSession) -> PieceOut:
    """Cambiar la fase de una pieza propia. La de otra persona responde 404."""
    return my_work.move_my_piece(db, ctx, piece_id, body.status)


@router.patch("/my-work/tasks/{task_id}")
def move_my_task(task_id: UUID, body: MyTaskUpdate, ctx: OwnWork, db: DbSession) -> TaskOut:
    """Marcar una tarea propia en curso o hecha. La de otra persona responde 404."""
    return my_work.move_my_task(db, ctx, task_id, body.status)


@router.get("/pieces/{piece_id}/updates")
def list_piece_updates(piece_id: UUID, ctx: OwnWork, db: DbSession) -> list[PieceUpdateOut]:
    """Los avances de la pieza (lo más nuevo primero). Los ve quien ve el evento o la tiene."""
    return updates.list_updates(db, ctx, piece_id)


@router.post("/pieces/{piece_id}/updates", status_code=status.HTTP_201_CREATED)
def add_piece_update(
    piece_id: UUID, body: PieceUpdateIn, ctx: OwnWork, db: DbSession
) -> PieceUpdateOut:
    """Subir un avance: foto y/o nota. Producción, o quien tiene la pieza asignada."""
    return updates.add_update(db, ctx, piece_id, body)


@router.get("/piece-updates/{update_id}/photo")
def get_piece_update_photo(update_id: UUID, ctx: OwnWork, db: DbSession) -> Response:
    """La foto de un avance (para verla en la ficha o en Mis tareas)."""
    return updates.update_photo(db, ctx, update_id)
