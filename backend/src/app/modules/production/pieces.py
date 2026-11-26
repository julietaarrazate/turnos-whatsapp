"""Piezas a medida del evento (mostrador, corpóreo, tarima…) y sus fases de fabricación."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select

from app.core.db import AppSession
from app.core.errors import not_found
from app.core.security import utcnow
from app.modules.auth import TenantContext
from app.modules.catalog import today_ar
from app.modules.events import get_event
from app.modules.identity import User
from app.modules.production.models import EventPiece, PieceArea, PieceStatus
from app.modules.production.schemas import PieceIn, PieceOut, PiecesOut, PieceUpdate
from app.modules.production.service import _audit, _check_assignee, _editable_event

# Avance de cada fase sobre 100 (diseño 0 … montado 100): el % del evento es el promedio.
_PHASES = list(PieceStatus)
_DONE = {PieceStatus.READY, PieceStatus.MOUNTED}


def _weight(status: PieceStatus) -> int:
    return round(_PHASES.index(status) * 100 / (len(_PHASES) - 1))


def summary(statuses: list[PieceStatus]) -> tuple[int, int, int]:
    """(total, listas, % de avance) de un conjunto de piezas."""
    total = len(statuses)
    if not total:
        return 0, 0, 0
    ready = sum(1 for s in statuses if s in _DONE)
    return total, ready, round(sum(_weight(s) for s in statuses) / total)


def _out(piece: EventPiece, assignee: str | None, today: date) -> PieceOut:
    status = PieceStatus(piece.status)
    return PieceOut(
        id=piece.id,
        event_id=piece.event_id,
        name=piece.name,
        area=PieceArea(piece.area),
        status=status,
        assignee_user_id=piece.assignee_user_id,
        assignee_name=assignee,
        due_date=piece.due_date,
        late=bool(piece.due_date and piece.due_date < today and status not in _DONE),
        notes=piece.notes,
        status_changed_at=piece.status_changed_at,
    )


def list_pieces(db: AppSession, ctx: TenantContext, event_id: UUID) -> PiecesOut:
    event = get_event(db, ctx, event_id)
    rows = db.execute(
        select(EventPiece, User.name)
        .outerjoin(User, User.id == EventPiece.assignee_user_id)
        .where(EventPiece.event_id == event.id, EventPiece.organization_id == ctx.organization_id)
        .order_by(EventPiece.sort, EventPiece.created_at)
    ).all()
    today = today_ar()
    pieces = [_out(p, name, today) for p, name in rows]
    total, ready, progress = summary([p.status for p in pieces])
    return PiecesOut(pieces=pieces, total=total, ready=ready, progress=progress)


def _piece(db: AppSession, ctx: TenantContext, piece_id: UUID) -> EventPiece:
    piece = db.execute(
        select(EventPiece)
        .where(EventPiece.id == piece_id, EventPiece.organization_id == ctx.organization_id)
        .with_for_update()
    ).scalar_one_or_none()
    if piece is None:
        raise not_found()
    return piece


def _with_name(db: AppSession, piece: EventPiece) -> PieceOut:
    name = (
        db.execute(select(User.name).where(User.id == piece.assignee_user_id)).scalar_one_or_none()
        if piece.assignee_user_id
        else None
    )
    return _out(piece, name, today_ar())


def add_piece(db: AppSession, ctx: TenantContext, event_id: UUID, body: PieceIn) -> PieceOut:
    _editable_event(db, ctx, event_id)
    _check_assignee(db, ctx, body.assignee_user_id)
    last = db.execute(
        select(func.max(EventPiece.sort)).where(
            EventPiece.event_id == event_id, EventPiece.organization_id == ctx.organization_id
        )
    ).scalar_one()
    piece = EventPiece(
        organization_id=ctx.organization_id,
        event_id=event_id,
        name=body.name.strip(),
        area=body.area.value,
        assignee_user_id=body.assignee_user_id,
        due_date=body.due_date,
        notes=(body.notes or "").strip() or None,
        sort=(last or 0) + 1,
    )
    db.add(piece)
    db.flush()
    _audit(db, ctx, "piece.created", event_id, after={"piece": piece.name, "area": piece.area})
    return _with_name(db, piece)


def update_piece(db: AppSession, ctx: TenantContext, piece_id: UUID, body: PieceUpdate) -> PieceOut:
    piece = _piece(db, ctx, piece_id)
    _editable_event(db, ctx, piece.event_id)
    fields = body.model_fields_set
    if "name" in fields and body.name:
        piece.name = body.name.strip()
    if "area" in fields and body.area:
        piece.area = body.area.value
    if "status" in fields and body.status and body.status.value != piece.status:
        _audit(
            db,
            ctx,
            "piece.status_changed",
            piece.event_id,
            before={"piece": piece.name, "status": piece.status},
            after={"piece": piece.name, "status": body.status.value},
        )
        piece.status = body.status.value
        piece.status_changed_at = utcnow()
    if "assignee_user_id" in fields:
        _check_assignee(db, ctx, body.assignee_user_id)
        piece.assignee_user_id = body.assignee_user_id
    if "due_date" in fields:
        piece.due_date = body.due_date
    if "notes" in fields:
        piece.notes = (body.notes or "").strip() or None
    db.flush()
    return _with_name(db, piece)


def delete_piece(db: AppSession, ctx: TenantContext, piece_id: UUID) -> None:
    piece = _piece(db, ctx, piece_id)
    _editable_event(db, ctx, piece.event_id)
    _audit(db, ctx, "piece.deleted", piece.event_id, before={"piece": piece.name})
    db.delete(piece)
    db.flush()
