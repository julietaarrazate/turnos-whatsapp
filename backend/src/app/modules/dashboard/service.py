"""Dashboard (A-01): pocos KPIs y mucha acción (PRODUCT_SPEC §4.1, métricas en §8).

Solo lectura: arma la vista con lo que exponen propuestas, presupuestos y eventos.
"""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from app.core.db import AppSession
from app.core.enums import Role
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.security import utcnow
from app.modules.auth import TenantContext
from app.modules.budgets import stale_cost_count, version_totals
from app.modules.catalog import today_ar
from app.modules.clients import Client
from app.modules.dashboard.schemas import (
    ActiveEvent,
    AmountOut,
    ConversionOut,
    DashboardOut,
    PendingOut,
    TodoOut,
    UpcomingEvent,
)
from app.modules.events import Event, EventStatus
from app.modules.identity import Organization
from app.modules.production import events_health, pending_operations
from app.modules.proposals import Amount, FollowUp, commercial_metrics

AR = ZoneInfo("America/Argentina/Buenos_Aires")
RATE = Decimal("0.000001")
CONVERSION_WINDOW = timedelta(days=90)
UPCOMING_LIMIT = 5
ACTIVE_LIMIT = 8
# Un evento que pasó hace más de esto y sigue "aprobado" quedó olvidado: no ocupa el pulso.
ACTIVE_PAST_DAYS = 14
_UPCOMING = (EventStatus.APPROVED, EventStatus.IN_PRODUCTION)


def _month_bounds(month: str | None) -> tuple[str, datetime, datetime]:
    """El mes (hora de Argentina) como intervalo `[inicio, fin)` en UTC."""
    if month is None:
        today = today_ar()
        first = date(today.year, today.month, 1)
    else:
        try:
            year, number = (int(part) for part in month.split("-"))
            first = date(year, number, 1)
        except ValueError as exc:
            raise AppError(422, "invalid_month", "El mes va como AAAA-MM") from exc
    following = date(first.year + first.month // 12, first.month % 12 + 1, 1)
    start = datetime.combine(first, time.min, tzinfo=AR)
    end = datetime.combine(following, time.min, tzinfo=AR)
    return f"{first:%Y-%m}", start, end


def _ratio(part: Decimal, whole: Decimal) -> Decimal | None:
    return (part / whole).quantize(RATE, rounding=ROUND_HALF_UP) if whole else None


def _amount(value: Amount) -> AmountOut:
    return AmountOut(count=value.count, amount=value.amount)


def _upcoming(db: AppSession, ctx: TenantContext) -> list[UpcomingEvent]:
    rows = db.execute(
        select(Event, Client.name)
        .join(Client, Client.id == Event.client_id)
        .where(
            Event.organization_id == ctx.organization_id,
            Event.deleted_at.is_(None),
            Event.status.in_([s.value for s in _UPCOMING]),
            Event.start_date >= today_ar(),
        )
        .order_by(Event.start_date, Event.number)
        .limit(UPCOMING_LIMIT)
    ).all()
    margins = ctx.can(Permission.MARGIN_VIEW)
    out = []
    for event, client_name in rows:
        totals = (
            version_totals(db, ctx.organization_id, event.accepted_budget_version_id)
            if margins and event.accepted_budget_version_id
            else None
        )
        out.append(
            UpcomingEvent(
                id=event.id,
                number=event.number,
                name=event.name,
                client_name=client_name,
                start_date=event.start_date,
                status=EventStatus(event.status),
                margin=totals.margin_net if totals else None,
            )
        )
    return out


def _active(db: AppSession, ctx: TenantContext) -> list[ActiveEvent]:
    """Lo que se está produciendo: aprobados y en producción, el montaje más cercano primero."""
    rows = db.execute(
        select(Event, Client.name)
        .join(Client, Client.id == Event.client_id)
        .where(
            Event.organization_id == ctx.organization_id,
            Event.deleted_at.is_(None),
            Event.status.in_([s.value for s in _UPCOMING]),
            or_(
                Event.start_date.is_(None),
                Event.start_date >= today_ar() - timedelta(days=ACTIVE_PAST_DAYS),
            ),
        )
        .order_by(Event.start_date.asc().nulls_last(), Event.number)
        .limit(ACTIVE_LIMIT)
    ).all()
    health = events_health(db, ctx, [event.id for event, _ in rows], today_ar())
    out = []
    for event, client_name in rows:
        h = health[event.id]
        out.append(
            ActiveEvent(
                id=event.id,
                number=event.number,
                name=event.name,
                client_name=client_name,
                status=EventStatus(event.status),
                start_date=event.start_date,
                mount_date=event.start_date - timedelta(days=event.setup_days)
                if event.start_date
                else None,
                pieces_total=h.total,
                pieces_ready=h.ready,
                progress=h.progress,
                late=h.late,
            )
        )
    return out


def dashboard(db: AppSession, ctx: TenantContext, month: str | None) -> DashboardOut:
    label, start, end = _month_bounds(month)
    own_only = ctx.role is Role.QUOTER  # "propio" (PRODUCT_SPEC §9)
    metrics = commercial_metrics(
        db,
        ctx,
        start=start,
        end=end,
        window_start=utcnow() - CONVERSION_WINDOW,
        own_only=own_only,
    )
    decided = metrics.won.count + metrics.lost.count
    org = db.get(Organization, ctx.organization_id)
    return DashboardOut(
        month=label,
        own_only=own_only,
        sent=_amount(metrics.sent),
        accepted=_amount(metrics.accepted),
        in_negotiation=_amount(metrics.in_negotiation),
        avg_margin=_ratio(metrics.accepted_profit, metrics.accepted.amount)
        if ctx.can(Permission.MARGIN_VIEW)
        else None,
        conversion=ConversionOut(
            won=_amount(metrics.won),
            lost=_amount(metrics.lost),
            by_count=_ratio(Decimal(metrics.won.count), Decimal(decided)),
            by_amount=_ratio(metrics.won.amount, metrics.won.amount + metrics.lost.amount),
        ),
        todo=TodoOut(
            no_response=metrics.follow_ups[FollowUp.NO_RESPONSE],
            viewed_no_answer=metrics.follow_ups[FollowUp.VIEWED_NO_ANSWER],
            expiring=metrics.follow_ups[FollowUp.EXPIRING],
            stale_costs=stale_cost_count(db, ctx, own_only=own_only)
            if ctx.can(Permission.COST_VIEW)
            else 0,
            follow_up_days=org.follow_up_days if org else 5,
            operations=[
                PendingOut(
                    kind=p.kind,
                    event_id=p.event_id,
                    event_number=p.event_number,
                    event_name=p.event_name,
                    count=p.count,
                    date=p.date,
                )
                for p in pending_operations(db, ctx, today_ar())
            ]
            if ctx.can(Permission.PRODUCTION_MANAGE)
            else [],
        ),
        upcoming=_upcoming(db, ctx),
        active=_active(db, ctx),
    )
