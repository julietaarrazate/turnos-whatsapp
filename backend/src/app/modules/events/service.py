"""Eventos: el contenedor del trabajo comercial y de producción (DOMAIN_MODEL §2.5, §3.1)."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, or_, select, tuple_

from app.core.counters import next_number
from app.core.db import AppSession
from app.core.enums import Role
from app.core.errors import AppError, not_found
from app.modules.audit import ActorType, diff, record
from app.modules.auth import ClientInfo, TenantContext
from app.modules.clients import Client, get_active, get_or_create_by_name
from app.modules.events.models import Event, EventStatus, EventStatusChange
from app.modules.events.schemas import (
    EventIn,
    EventOut,
    EventPage,
    EventSummary,
    EventUpdate,
    StatusChangeIn,
    StatusChangeOut,
)
from app.modules.identity import Membership, MembershipStatus, User

S = EventStatus


class Actor(Protocol):
    """Quién dispara un cambio: un usuario (TenantContext) o el cliente desde el link público
    (sin usuario)."""

    @property
    def organization_id(self) -> UUID: ...
    @property
    def user_id(self) -> UUID | None: ...
    @property
    def client(self) -> ClientInfo: ...


# Transiciones manuales (§3.1). Las automáticas las disparan presupuestos y propuestas.
_MANUAL: dict[EventStatus, set[EventStatus]] = {
    S.LOST: {S.LEAD, S.QUOTING, S.SENT, S.NEGOTIATION},
    S.CANCELLED: {S.LEAD, S.QUOTING, S.APPROVED, S.IN_PRODUCTION},
    S.QUOTING: {S.LOST},  # reabrir
}
_REASON_REQUIRED = {S.LOST, S.CANCELLED}

_FIELDS = (
    "client_id",
    "name",
    "start_date",
    "end_date",
    "event_days",
    "setup_days",
    "teardown_days",
    "venue",
    "city",
    "responsible_user_id",
    "notes",
)
_REQUIRED = {"client_id", "name", "event_days", "setup_days", "teardown_days"}


def _audit(db: AppSession, ctx: Actor, action: str, entity_id: UUID, **changes: Any) -> None:
    record(
        db,
        organization_id=ctx.organization_id,
        action=action,
        entity_type="event",
        entity_id=entity_id,
        actor_user_id=ctx.user_id,
        actor_type=ActorType.USER if ctx.user_id else ActorType.PUBLIC_TOKEN,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
        **changes,
    )


def _jsonable(values: dict[str, Any]) -> dict[str, Any]:
    return {
        k: (str(v) if v is not None and not isinstance(v, str | int) else v)
        for k, v in values.items()
    }


def get_event(db: AppSession, ctx: Actor, event_id: UUID, *, for_update: bool = False) -> Event:
    query = select(Event).where(
        Event.id == event_id,
        Event.organization_id == ctx.organization_id,
        Event.deleted_at.is_(None),
    )
    event = db.execute(query.with_for_update() if for_update else query).scalar_one_or_none()
    if event is None:
        raise not_found()
    return event


def _check_responsible(db: AppSession, ctx: TenantContext, user_id: UUID | None) -> None:
    if user_id is None:
        return
    member = db.execute(
        select(Membership.id).where(
            Membership.organization_id == ctx.organization_id,
            Membership.user_id == user_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if member is None:
        raise AppError(
            422, "responsible_not_member", "La persona responsable no es de la organización"
        )


def _set_status(
    db: AppSession, ctx: Actor, event: Event, to: EventStatus, reason: str | None = None
) -> None:
    previous = event.status
    event.status = to.value
    db.add(
        EventStatusChange(
            organization_id=ctx.organization_id,
            event_id=event.id,
            from_status=previous,
            to_status=to.value,
            changed_by=ctx.user_id,
            reason=reason,
        )
    )
    _audit(
        db,
        ctx,
        "event.status_changed",
        event.id,
        before={"status": previous},
        after={"status": to.value, "reason": reason},
    )


# --- Lectura -------------------------------------------------------------------------------


def _summary(event: Event, client_name: str, responsible: str | None) -> EventSummary:
    return EventSummary(
        id=event.id,
        number=event.number,
        name=event.name,
        client_id=event.client_id,
        client_name=client_name,
        start_date=event.start_date,
        end_date=event.end_date,
        event_days=event.event_days,
        city=event.city,
        status=EventStatus(event.status),
        responsible_name=responsible,
    )


def _encode_cursor(event: Event) -> str:
    return urlsafe_b64encode(f"{event.created_at.isoformat()}|{event.id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        created, raw_id = urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(created), UUID(raw_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(422, "invalid_cursor", "Cursor inválido") from exc


def list_events(
    db: AppSession,
    ctx: TenantContext,
    *,
    q: str | None,
    status: list[EventStatus] | None,
    client_id: UUID | None,
    cursor: str | None,
    limit: int,
) -> EventPage:
    query = (
        select(Event, Client.name, User.name)
        .join(Client, Client.id == Event.client_id)
        .outerjoin(User, User.id == Event.responsible_user_id)
        .where(Event.organization_id == ctx.organization_id, Event.deleted_at.is_(None))
    )
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        query = query.where(
            or_(func.lower(Event.name).like(pattern), func.lower(Client.name).like(pattern))
        )
    if status:
        query = query.where(Event.status.in_([s.value for s in status]))
    if client_id is not None:
        query = query.where(Event.client_id == client_id)
    if cursor:
        created, last_id = _decode_cursor(cursor)
        query = query.where(tuple_(Event.created_at, Event.id) < tuple_(created, last_id))
    rows = db.execute(
        query.order_by(Event.created_at.desc(), Event.id.desc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    return EventPage(
        items=[_summary(e, client, responsible) for e, client, responsible in page],
        next_cursor=_encode_cursor(page[-1][0]) if len(rows) > limit else None,
    )


def event_out(db: AppSession, ctx: TenantContext, event: Event) -> EventOut:
    client_name = db.execute(select(Client.name).where(Client.id == event.client_id)).scalar_one()
    responsible = (
        db.execute(
            select(User.name).where(User.id == event.responsible_user_id)
        ).scalar_one_or_none()
        if event.responsible_user_id
        else None
    )
    history = db.execute(
        select(EventStatusChange, User.name)
        .outerjoin(User, User.id == EventStatusChange.changed_by)
        .where(EventStatusChange.event_id == event.id)
        .order_by(EventStatusChange.at, EventStatusChange.id)
    ).all()
    summary = _summary(event, client_name, responsible)
    return EventOut(
        **summary.model_dump(),
        setup_days=event.setup_days,
        teardown_days=event.teardown_days,
        venue=event.venue,
        responsible_user_id=event.responsible_user_id,
        lost_reason=event.lost_reason,
        cancel_reason=event.cancel_reason,
        notes=event.notes,
        accepted_budget_version_id=event.accepted_budget_version_id,
        history=[
            StatusChangeOut(
                from_status=EventStatus(h.from_status) if h.from_status else None,
                to_status=EventStatus(h.to_status),
                changed_by_name=name,
                reason=h.reason,
                at=h.at,
            )
            for h, name in history
        ],
    )


# --- Escritura -----------------------------------------------------------------------------


def create_event(db: AppSession, ctx: TenantContext, body: EventIn) -> Event:
    if body.client_id is not None:
        client = get_active(db, ctx, body.client_id)
    else:
        client = get_or_create_by_name(db, ctx, body.client_name or "")
    responsible = body.responsible_user_id or ctx.user_id
    _check_responsible(db, ctx, responsible)
    event = Event(
        organization_id=ctx.organization_id,
        number=next_number(db, ctx.organization_id, "event"),
        client_id=client.id,
        name=body.name.strip(),
        start_date=body.start_date,
        end_date=body.end_date,
        event_days=body.event_days,
        setup_days=body.setup_days,
        teardown_days=body.teardown_days,
        venue=body.venue,
        city=body.city,
        responsible_user_id=responsible,
        notes=body.notes,
        status=EventStatus.LEAD.value,
    )
    db.add(event)
    db.flush()
    db.add(
        EventStatusChange(
            organization_id=ctx.organization_id,
            event_id=event.id,
            from_status=None,
            to_status=EventStatus.LEAD.value,
            changed_by=ctx.user_id,
        )
    )
    _audit(db, ctx, "event.created", event.id, after={"number": event.number, "name": event.name})
    db.flush()
    db.refresh(event)
    return event


def update_event(db: AppSession, ctx: TenantContext, event_id: UUID, body: EventUpdate) -> EventOut:
    event = get_event(db, ctx, event_id)
    fields = body.model_fields_set & set(_FIELDS)
    for field in fields & _REQUIRED:
        if getattr(body, field) is None:
            raise AppError(422, "field_required", f"{field} no puede quedar vacío")
    if "client_id" in fields and body.client_id is not None:
        get_active(db, ctx, body.client_id)
    if "responsible_user_id" in fields:
        _check_responsible(db, ctx, body.responsible_user_id)
    before = _jsonable({f: getattr(event, f) for f in fields})
    for field in fields:
        value = getattr(body, field)
        setattr(event, field, value.strip() if field == "name" else value)
    if event.start_date and event.end_date and event.end_date < event.start_date:
        raise AppError(422, "dates_invalid", "La fecha de fin no puede ser anterior a la de inicio")
    db.flush()
    old, new = diff(before, _jsonable({f: getattr(event, f) for f in fields}))
    if new:
        _audit(db, ctx, "event.updated", event.id, before=old, after=new)
    return event_out(db, ctx, event)


def change_status(
    db: AppSession, ctx: TenantContext, event_id: UUID, body: StatusChangeIn
) -> EventOut:
    event = get_event(db, ctx, event_id, for_update=True)
    current = EventStatus(event.status)
    allowed_from = _MANUAL.get(body.to_status)
    if allowed_from is None or current not in allowed_from:
        raise AppError(
            409,
            "event_transition_invalid",
            f"No se puede pasar de {current.value} a {body.to_status.value}",
        )
    reason = (body.reason or "").strip() or None
    if body.to_status in _REASON_REQUIRED and reason is None:
        raise AppError(422, "reason_required", "Indicá el motivo")
    if body.to_status is EventStatus.LOST:
        event.lost_reason = reason
    elif body.to_status is EventStatus.CANCELLED:
        event.cancel_reason = reason
    else:
        event.lost_reason = None
    _set_status(db, ctx, event, body.to_status, reason)
    db.flush()
    return event_out(db, ctx, event)


def _advance(
    db: AppSession,
    ctx: TenantContext,
    event_id: UUID,
    expected: EventStatus,
    to: EventStatus,
    *,
    reason: str | None = None,
) -> Event:
    """Transición manual del ciclo de producción (§3.1): solo desde el estado esperado."""
    event = get_event(db, ctx, event_id, for_update=True)
    current = EventStatus(event.status)
    if current is not expected:
        raise AppError(
            409,
            "event_transition_invalid",
            f"No se puede pasar de {current.value} a {to.value}",
        )
    _set_status(db, ctx, event, to, reason)
    db.flush()
    return event


def start_production(db: AppSession, ctx: TenantContext, event_id: UUID) -> EventOut:
    """APPROVED → IN_PRODUCTION. Parte de la versión aceptada (la baseline)."""
    event = get_event(db, ctx, event_id)
    if event.status == S.APPROVED and event.accepted_budget_version_id is None:
        raise AppError(409, "no_baseline", "El evento no tiene un presupuesto aprobado")
    return event_out(db, ctx, _advance(db, ctx, event_id, S.APPROVED, S.IN_PRODUCTION))


def complete(db: AppSession, ctx: TenantContext, event_id: UUID) -> EventOut:
    """IN_PRODUCTION → COMPLETED: el evento se hizo; se siguen cargando costos."""
    return event_out(db, ctx, _advance(db, ctx, event_id, S.IN_PRODUCTION, S.COMPLETED))


def close(db: AppSession, ctx: TenantContext, event_id: UUID) -> EventOut:
    """COMPLETED → CLOSED: cierre financiero; los costos quedan de solo lectura."""
    return event_out(db, ctx, _advance(db, ctx, event_id, S.COMPLETED, S.CLOSED))


def reopen(db: AppSession, ctx: TenantContext, event_id: UUID, reason: str) -> EventOut:
    """CLOSED → COMPLETED, con motivo (queda en el historial y en el audit)."""
    reason = reason.strip()
    if not reason:
        raise AppError(422, "reason_required", "Indicá el motivo")
    return event_out(db, ctx, _advance(db, ctx, event_id, S.CLOSED, S.COMPLETED, reason=reason))


def on_budget_created(db: AppSession, ctx: TenantContext, event_id: UUID) -> None:
    """§6 `BudgetCreated`: LEAD → QUOTING (automático)."""
    event = get_event(db, ctx, event_id, for_update=True)
    if event.status == EventStatus.LEAD:
        _set_status(db, ctx, event, EventStatus.QUOTING)


def can_quote(event: Event) -> bool:
    """Se pueden armar presupuestos mientras el evento no está cerrado, perdido ni cancelado."""
    return EventStatus(event.status) not in {S.LOST, S.CANCELLED, S.CLOSED, S.COMPLETED}


def on_proposal_sent(db: AppSession, ctx: TenantContext, event_id: UUID) -> None:
    """§6 `ProposalSent`: la primera propuesta lleva a SENT; las siguientes, a NEGOTIATION."""
    event = get_event(db, ctx, event_id, for_update=True)
    current = EventStatus(event.status)
    if current in {S.LEAD, S.QUOTING}:
        _set_status(db, ctx, event, S.SENT)
    elif current is S.SENT:
        _set_status(db, ctx, event, S.NEGOTIATION)


# Mientras el evento está en estas etapas, el cliente puede aceptar o rechazar online.
_DECIDABLE = {S.SENT, S.NEGOTIATION}
# La aprobación manual además cubre adicionales: cambia la baseline de un evento aprobado.
_MANUALLY_APPROVABLE = _DECIDABLE | {S.APPROVED, S.IN_PRODUCTION}


def accepts_decisions(db: AppSession, ctx: Actor, event_id: UUID, *, manual: bool) -> bool:
    event = get_event(db, ctx, event_id)
    allowed = _MANUALLY_APPROVABLE if manual else _DECIDABLE
    return EventStatus(event.status) in allowed


def on_proposal_accepted(db: AppSession, ctx: Actor, event_id: UUID, version_id: UUID) -> None:
    """§6 `ProposalAccepted`: la versión pasa a ser la baseline y el evento, APPROVED. Con el
    evento ya aprobado o en producción (adicionales) solo cambia la baseline."""
    event = get_event(db, ctx, event_id, for_update=True)
    current = EventStatus(event.status)
    if current not in _MANUALLY_APPROVABLE:
        raise AppError(
            409, "event_not_open", "El evento ya no admite aprobar propuestas en este estado"
        )
    previous = event.accepted_budget_version_id
    event.accepted_budget_version_id = version_id
    if current in _DECIDABLE:
        _set_status(db, ctx, event, S.APPROVED)
    _audit(
        db,
        ctx,
        "event.baseline_changed",
        event.id,
        before={"accepted_budget_version_id": str(previous) if previous else None},
        after={"accepted_budget_version_id": str(version_id)},
    )


def notification_recipients(
    db: AppSession, ctx: Actor, event_id: UUID, *, include_owners: bool
) -> tuple[str, list[str]]:
    """Nombre del evento y a quién avisar: el responsable (o los OWNER si no tiene) y,
    si se pide, también los OWNER."""
    event = get_event(db, ctx, event_id)
    emails: list[str] = []
    if event.responsible_user_id is not None:
        email = db.execute(
            select(User.email).where(User.id == event.responsible_user_id)
        ).scalar_one_or_none()
        if email:
            emails.append(email)
    if include_owners or not emails:
        owners = db.execute(
            select(User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == ctx.organization_id,
                Membership.role == Role.OWNER.value,
                Membership.status == MembershipStatus.ACTIVE,
            )
            .order_by(User.email)
        ).scalars()
        emails.extend(e for e in owners if e not in emails)
    return event.name, emails
