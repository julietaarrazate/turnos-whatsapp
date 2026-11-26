"""Actividad: lo que pasa en producción, en una lista ("Vale pasó el Mostrador a En taller").

Sale del audit log (append-only), filtrado a las acciones de producción y sin datos de plata.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.db import AppSession
from app.modules.audit import AuditLog
from app.modules.auth import TenantContext
from app.modules.events import Event
from app.modules.identity import User
from app.modules.production.schemas import ActivityEvent, ActivityOut, ActivityPage

KINDS = (
    "piece.created",
    "piece.status_changed",
    "piece.update_posted",
    "piece.plan_uploaded",
    "production.started",
    "production.supplier_status",
)
PAGE = 30


def _text(data: dict[str, Any] | None, key: str) -> str | None:
    value = (data or {}).get(key)
    return str(value) if value not in (None, "") else None


def _uuid(data: dict[str, Any] | None, key: str) -> UUID | None:
    value = _text(data, key)
    try:
        return UUID(value) if value else None
    except ValueError:
        return None


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
                created_at=log.created_at,
            )
        )
    more = len(rows) > PAGE
    return ActivityPage(items=items, next_before=items[-1].created_at if more and items else None)
