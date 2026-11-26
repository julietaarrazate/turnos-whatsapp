"""Actividad: lo que pasa en producción, en una lista ("Vale pasó el Mostrador a En taller").

Sale del audit log (append-only), filtrado a las acciones de producción y sin datos de plata.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.db import AppSession
from app.core.ids import uuid7
from app.core.security import utcnow
from app.modules.audit import AuditLog
from app.modules.auth import TenantContext
from app.modules.events import Event
from app.modules.identity import User
from app.modules.production.models import ActivityRead
from app.modules.production.schemas import ActivityEvent, ActivityOut, ActivityPage, UnreadOut

KINDS = (
    "piece.created",
    "piece.status_changed",
    "piece.update_posted",
    "piece.plan_uploaded",
    "production.started",
    "production.supplier_status",
)
PAGE = 30
UNREAD_CAP = 99


def _text(data: dict[str, Any] | None, key: str) -> str | None:
    value = (data or {}).get(key)
    return str(value) if value not in (None, "") else None


def _uuid(data: dict[str, Any] | None, key: str) -> UUID | None:
    value = _text(data, key)
    try:
        return UUID(value) if value else None
    except ValueError:
        return None


def _production_moves(ctx: TenantContext) -> Select[UUID]:
    return (
        select(AuditLog.id)
        .join(Event, Event.id == AuditLog.entity_id)
        .where(
            AuditLog.organization_id == ctx.organization_id,
            AuditLog.entity_type == "event",
            AuditLog.action.in_(KINDS),
            Event.organization_id == ctx.organization_id,
            Event.deleted_at.is_(None),
        )
    )


def _seen_at(db: AppSession, ctx: TenantContext) -> datetime | None:
    return db.execute(
        select(ActivityRead.seen_at).where(
            ActivityRead.organization_id == ctx.organization_id,
            ActivityRead.user_id == ctx.user_id,
        )
    ).scalar_one_or_none()


def unread(db: AppSession, ctx: TenantContext) -> UnreadOut:
    """Movimientos de otros desde la última vez (los propios no avisan). Si nunca miró, solo
    los de la última semana: alguien nuevo no arranca con cientos de avisos."""
    seen = _seen_at(db, ctx)
    since = seen or utcnow() - timedelta(days=7)
    moves = (
        _production_moves(ctx)
        .where(
            AuditLog.created_at > since,
            AuditLog.actor_user_id.is_distinct_from(ctx.user_id),
        )
        .limit(UNREAD_CAP)
        .subquery()
    )
    count = db.execute(select(func.count()).select_from(moves)).scalar_one()
    return UnreadOut(count=count, seen_at=seen)


def mark_seen(db: AppSession, ctx: TenantContext) -> UnreadOut:
    now = utcnow()
    db.execute(
        insert(ActivityRead)
        .values(id=uuid7(), organization_id=ctx.organization_id, user_id=ctx.user_id, seen_at=now)
        .on_conflict_do_update(index_elements=["organization_id", "user_id"], set_={"seen_at": now})
    )
    return UnreadOut(count=0, seen_at=now)


def feed(
    db: AppSession, ctx: TenantContext, before: datetime | None, event_id: UUID | None
) -> ActivityPage:
    query = (
        select(AuditLog, User.name, Event)
        .join(Event, Event.id == AuditLog.entity_id)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(
            AuditLog.organization_id == ctx.organization_id,
            AuditLog.entity_type == "event",
            AuditLog.action.in_(KINDS),
            Event.organization_id == ctx.organization_id,
            Event.deleted_at.is_(None),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(PAGE + 1)
    )
    if before is not None:
        query = query.where(AuditLog.created_at < before)
    if event_id is not None:
        query = query.where(AuditLog.entity_id == event_id)
    rows = db.execute(query).all()
    items = []
    for log, actor, event in rows[:PAGE]:
        after = log.after
        version = (after or {}).get("version")
        items.append(
            ActivityOut(
                id=log.id,
                kind=log.action,
                actor_name=actor,
                event=ActivityEvent(id=event.id, number=event.number, name=event.name),
                piece=_text(after, "piece"),
                status=_text(after, "status"),
                supplier=_text(after, "supplier"),
                title=_text(after, "title"),
                version=version if isinstance(version, int) else None,
                note=_text(after, "note"),
                update_id=_uuid(after, "update_id"),
                has_photo=bool((after or {}).get("photo")),
                has_audio=bool((after or {}).get("audio")),
                created_at=log.created_at,
            )
        )
    more = len(rows) > PAGE
    return ActivityPage(items=items, next_before=items[-1].created_at if more and items else None)
