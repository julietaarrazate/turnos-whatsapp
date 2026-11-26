"""Mis tareas: lo que tiene asignado cada persona (taller, montaje), sin presupuestos ni plata.

Solo se ve y se mueve lo propio: una pieza o tarea de otra persona responde 404, igual que
una de otra organización.
"""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, select

from app.core.db import AppSession
from app.core.errors import not_found
from app.modules.auth import TenantContext
from app.modules.catalog import today_ar
from app.modules.events import Event, EventStatus
from app.modules.production import pieces, service
from app.modules.production.models import (
    EventPiece,
    PieceArea,
    PieceStatus,
    ProductionTask,
    TaskStatus,
)
from app.modules.production.schemas import (
    MyPiece,
    MyTask,
    MyWorkOut,
    PieceOut,
    PieceUpdate,
    TaskOut,
    TaskUpdate,
    WorkEvent,
)

_CLOSED = (EventStatus.CLOSED.value, EventStatus.CANCELLED.value)
_PIECE_DONE = PieceStatus.MOUNTED.value  # "lista para carga" todavía hay que montarla


def _event(event: Event) -> WorkEvent:
    mount = event.start_date - timedelta(days=event.setup_days) if event.start_date else None
    return WorkEvent(id=event.id, number=event.number, name=event.name, mount_date=mount)


def _open_events(ctx: TenantContext) -> tuple[ColumnElement[bool], ...]:
    return (
        Event.organization_id == ctx.organization_id,
        Event.deleted_at.is_(None),
        Event.status.not_in(_CLOSED),
    )


def _key(due: date | None, late: bool, event: WorkEvent) -> tuple[bool, date, date]:
    """Lo atrasado primero, después por vencimiento y por montaje; sin fecha, al final."""
    far = date.max
    return (not late, due or far, event.mount_date or far)


def my_work(db: AppSession, ctx: TenantContext) -> MyWorkOut:
    today = today_ar()
    piece_rows = db.execute(
        select(EventPiece, Event)
        .join(Event, Event.id == EventPiece.event_id)
        .where(
            EventPiece.organization_id == ctx.organization_id,
            EventPiece.assignee_user_id == ctx.user_id,
            EventPiece.status != _PIECE_DONE,
            *_open_events(ctx),
        )
    ).all()
    my_pieces = []
    for piece, event in piece_rows:
        status = PieceStatus(piece.status)
        my_pieces.append(
            MyPiece(
                id=piece.id,
                name=piece.name,
                area=PieceArea(piece.area),
                status=status,
                due_date=piece.due_date,
                late=pieces.is_late(piece.due_date, status, today),
                notes=piece.notes,
                event=_event(event),
            )
        )
    task_rows = db.execute(
        select(ProductionTask, Event)
        .join(Event, Event.id == ProductionTask.event_id)
        .where(
            ProductionTask.organization_id == ctx.organization_id,
            ProductionTask.assignee_user_id == ctx.user_id,
            ProductionTask.status != TaskStatus.DONE.value,
            *_open_events(ctx),
        )
    ).all()
    my_tasks = [
        MyTask(
            id=task.id,
            title=task.title,
            status=TaskStatus(task.status),
            due_date=task.due_date,
            late=bool(task.due_date and task.due_date < today),
            event=_event(event),
        )
        for task, event in task_rows
    ]
    my_pieces.sort(key=lambda p: _key(p.due_date, p.late, p.event))
    my_tasks.sort(key=lambda t: _key(t.due_date, t.late, t.event))
    return MyWorkOut(pieces=my_pieces, tasks=my_tasks)


def _assigned(
    db: AppSession, ctx: TenantContext, model: type[EventPiece] | type[ProductionTask], row_id: UUID
) -> None:
    owner = db.execute(
        select(model.assignee_user_id).where(
            model.id == row_id, model.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if owner is None or owner != ctx.user_id:
        raise not_found()


def move_my_piece(
    db: AppSession, ctx: TenantContext, piece_id: UUID, status: PieceStatus
) -> PieceOut:
    """Cambiar la fase de una pieza propia (queda en la auditoría como cualquier cambio)."""
    _assigned(db, ctx, EventPiece, piece_id)
    return pieces.update_piece(db, ctx, piece_id, PieceUpdate(status=status))


def move_my_task(db: AppSession, ctx: TenantContext, task_id: UUID, status: TaskStatus) -> TaskOut:
    _assigned(db, ctx, ProductionTask, task_id)
    return service.update_task(db, ctx, task_id, TaskUpdate(status=status))
