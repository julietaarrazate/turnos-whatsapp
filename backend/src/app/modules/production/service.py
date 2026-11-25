"""Producción liviana (PRODUCT_SPEC §4.9): lista de contratación por proveedor y tareas.

Todo sale de la versión aceptada (la baseline) sin volver a cargar nada (P1).
"""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.core.permissions import Permission
from app.core.security import utcnow
from app.modules.audit import record
from app.modules.auth import TenantContext
from app.modules.budgets import BaselineLine, baseline_lines
from app.modules.catalog import SupplierContactInfo, primary_contacts
from app.modules.events import Event, EventStatus, get_event, start_production
from app.modules.identity import Membership, MembershipStatus, User
from app.modules.production.models import EventSupplier, HireStatus, ProductionTask, TaskStatus
from app.modules.production.schemas import (
    EventSupplierOut,
    EventSupplierUpdate,
    HireItem,
    ProductionOut,
    TaskIn,
    TaskOut,
    TaskUpdate,
)

# Tareas que casi todo evento necesita; se suman las de cada categoría de la baseline.
_GENERIC_TASKS = (
    "Confirmar con el cliente los horarios de armado y desarme",
    "Enviar a los proveedores la ubicación, los accesos y los horarios",
)
# Siempre hacia adelante (se puede saltear un paso: llega la factura sin confirmar antes).
_HIRE_ORDER = [HireStatus.TO_HIRE, HireStatus.CONFIRMED, HireStatus.INVOICED, HireStatus.PAID]


def _hire_allowed(current: HireStatus, target: HireStatus) -> bool:
    if target is HireStatus.CANCELLED:
        return current in {HireStatus.TO_HIRE, HireStatus.CONFIRMED}
    if current is HireStatus.CANCELLED:
        return False
    return _HIRE_ORDER.index(target) > _HIRE_ORDER.index(current)


_LOCKED = {EventStatus.CLOSED, EventStatus.CANCELLED}


def _audit(
    db: AppSession, ctx: TenantContext, action: str, entity_id: UUID, **changes: Any
) -> None:
    record(
        db,
        organization_id=ctx.organization_id,
        action=action,
        entity_type="event",
        entity_id=entity_id,
        actor_user_id=ctx.user_id,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
        **changes,
    )


def _group_by_supplier(
    lines: list[BaselineLine],
) -> list[tuple[UUID | None, str | None, list[BaselineLine]]]:
    groups: OrderedDict[UUID | None, tuple[str | None, list[BaselineLine]]] = OrderedDict()
    for line in lines:
        _, items = groups.setdefault(line.supplier_id, (line.supplier_name, []))
        items.append(line)
    return [(supplier_id, name, items) for supplier_id, (name, items) in groups.items()]


def start(db: AppSession, ctx: TenantContext, event_id: UUID) -> ProductionOut:
    """§6 `ProductionStarted`: el evento pasa a IN_PRODUCTION y se arma la lista de contratación
    (agrupada por proveedor, con el costo presupuestado) y las tareas sugeridas."""
    start_production(db, ctx, event_id)
    event = get_event(db, ctx, event_id)
    if event.accepted_budget_version_id is None:  # start_production ya lo verificó
        raise AppError(409, "no_baseline", "El evento no tiene un presupuesto aprobado")
    lines = baseline_lines(db, ctx.organization_id, event.accepted_budget_version_id)

    for sort, (supplier_id, supplier_name, items) in enumerate(_group_by_supplier(lines)):
        db.add(
            EventSupplier(
                organization_id=ctx.organization_id,
                event_id=event.id,
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                status=HireStatus.TO_HIRE.value,
                budgeted_cost=sum((i.cost_total for i in items), Decimal(0)),
                items=[
                    {
                        "line_key": str(i.line_key),
                        "name": i.name,
                        "quantity": str(i.quantity),
                        "unit_code": i.unit_code,
                        "days": i.days,
                        "cost_total": str(i.cost_total),
                    }
                    for i in items
                ],
                sort=sort,
            )
        )

    categories: OrderedDict[UUID, str] = OrderedDict()
    for line in lines:
        if line.category_id and line.category_name:
            categories.setdefault(line.category_id, line.category_name)
    due = event.start_date - timedelta(days=2) if event.start_date else None
    titles: list[tuple[str, UUID | None]] = [(t, None) for t in _GENERIC_TASKS]
    titles += [(f"Coordinar {name.lower()}", cid) for cid, name in categories.items()]
    for sort, (title, category_id) in enumerate(titles):
        db.add(
            ProductionTask(
                organization_id=ctx.organization_id,
                event_id=event.id,
                title=title[:200],
                category_id=category_id,
                due_date=due,
                sort=sort,
            )
        )
    db.flush()
    _audit(db, ctx, "production.started", event.id, after={"suppliers": len(lines)})
    return production(db, ctx, event_id)


def production(db: AppSession, ctx: TenantContext, event_id: UUID) -> ProductionOut:
    event = get_event(db, ctx, event_id)
    costs = ctx.can(Permission.COST_VIEW)
    suppliers = (
        db.execute(
            select(EventSupplier)
            .where(
                EventSupplier.event_id == event.id,
                EventSupplier.organization_id == ctx.organization_id,
            )
            .order_by(EventSupplier.sort)
        )
        .scalars()
        .all()
    )
    tasks = db.execute(
        select(ProductionTask, User.name)
        .outerjoin(User, User.id == ProductionTask.assignee_user_id)
        .where(
            ProductionTask.event_id == event.id,
            ProductionTask.organization_id == ctx.organization_id,
        )
        .order_by(ProductionTask.sort, ProductionTask.created_at)
    ).all()
    active = [s for s in suppliers if s.status != HireStatus.CANCELLED]
    contacts = primary_contacts(db, ctx, [s.supplier_id for s in suppliers if s.supplier_id])
    return ProductionOut(
        started=bool(suppliers) or bool(tasks),
        suppliers=[_supplier_out(s, costs=costs, contacts=contacts) for s in suppliers],
        tasks=[_task_out(t, name) for t, name in tasks],
        budgeted_cost=sum((s.budgeted_cost for s in active), Decimal(0)) if costs else None,
    )


def _supplier_out(
    row: EventSupplier, *, costs: bool, contacts: dict[UUID, SupplierContactInfo]
) -> EventSupplierOut:
    contact = contacts.get(row.supplier_id) if row.supplier_id else None
    return EventSupplierOut(
        id=row.id,
        supplier_id=row.supplier_id,
        supplier_name=row.supplier_name,
        contact_name=contact.name if contact else None,
        contact_phone=contact.phone if contact else None,
        status=HireStatus(row.status),
        budgeted_cost=row.budgeted_cost if costs else None,
        items=[
            HireItem(
                line_key=item["line_key"],
                name=item["name"],
                quantity=Decimal(item["quantity"]),
                unit_code=item["unit_code"],
                days=item["days"],
                cost_total=Decimal(item["cost_total"]) if costs else None,
            )
            for item in row.items
        ],
        notes=row.notes,
        invoice_number=row.invoice_number,
        payment_terms=row.payment_terms,
        confirmed_at=row.confirmed_at,
        paid_at=row.paid_at,
    )


def _task_out(task: ProductionTask, assignee: str | None) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        status=TaskStatus(task.status),
        assignee_user_id=task.assignee_user_id,
        assignee_name=assignee,
        due_date=task.due_date,
    )


def _editable_event(db: AppSession, ctx: TenantContext, event_id: UUID) -> None:
    event = get_event(db, ctx, event_id)
    if EventStatus(event.status) in _LOCKED:
        raise AppError(409, "event_locked", "El evento está cerrado o cancelado")


def update_supplier(
    db: AppSession, ctx: TenantContext, row_id: UUID, body: EventSupplierUpdate
) -> EventSupplierOut:
    row = db.execute(
        select(EventSupplier)
        .where(EventSupplier.id == row_id, EventSupplier.organization_id == ctx.organization_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    _editable_event(db, ctx, row.event_id)
    if body.status is not None and body.status != row.status:
        current = HireStatus(row.status)
        if not _hire_allowed(current, body.status):
            raise AppError(
                409, "hire_transition_invalid", f"No se puede pasar de {current} a {body.status}"
            )
        row.status = body.status.value
        now = utcnow()
        if body.status is HireStatus.CONFIRMED or (
            body.status in {HireStatus.INVOICED, HireStatus.PAID} and row.confirmed_at is None
        ):
            row.confirmed_at = now
        if body.status is HireStatus.PAID:
            row.paid_at = now
        _audit(
            db,
            ctx,
            "production.supplier_status",
            row.event_id,
            before={"supplier": row.supplier_name, "status": current.value},
            after={"supplier": row.supplier_name, "status": body.status.value},
        )
    for field in ("notes", "invoice_number", "payment_terms"):
        if field in body.model_fields_set:
            setattr(row, field, (getattr(body, field) or "").strip() or None)
    db.flush()
    contacts = primary_contacts(db, ctx, [row.supplier_id] if row.supplier_id else [])
    return _supplier_out(row, costs=ctx.can(Permission.COST_VIEW), contacts=contacts)


def _check_assignee(db: AppSession, ctx: TenantContext, user_id: UUID | None) -> None:
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
        raise AppError(422, "assignee_not_member", "La persona no es de la organización")


def _task(db: AppSession, ctx: TenantContext, task_id: UUID) -> ProductionTask:
    task = db.execute(
        select(ProductionTask)
        .where(ProductionTask.id == task_id, ProductionTask.organization_id == ctx.organization_id)
        .with_for_update()
    ).scalar_one_or_none()
    if task is None:
        raise not_found()
    return task


def _task_with_name(db: AppSession, task: ProductionTask) -> TaskOut:
    name = (
        db.execute(select(User.name).where(User.id == task.assignee_user_id)).scalar_one_or_none()
        if task.assignee_user_id
        else None
    )
    return _task_out(task, name)


def add_task(db: AppSession, ctx: TenantContext, event_id: UUID, body: TaskIn) -> TaskOut:
    _editable_event(db, ctx, event_id)
    _check_assignee(db, ctx, body.assignee_user_id)
    last = db.execute(
        select(ProductionTask.sort)
        .where(
            ProductionTask.event_id == event_id,
            ProductionTask.organization_id == ctx.organization_id,
        )
        .order_by(ProductionTask.sort.desc())
        .limit(1)
    ).scalar_one_or_none()
    task = ProductionTask(
        organization_id=ctx.organization_id,
        event_id=event_id,
        title=body.title.strip(),
        assignee_user_id=body.assignee_user_id,
        due_date=body.due_date,
        sort=(last or 0) + 1,
    )
    db.add(task)
    db.flush()
    return _task_with_name(db, task)


def update_task(db: AppSession, ctx: TenantContext, task_id: UUID, body: TaskUpdate) -> TaskOut:
    task = _task(db, ctx, task_id)
    _editable_event(db, ctx, task.event_id)
    fields = body.model_fields_set
    if "title" in fields and body.title:
        task.title = body.title.strip()
    if "status" in fields and body.status:
        task.status = body.status.value
    if "assignee_user_id" in fields:
        _check_assignee(db, ctx, body.assignee_user_id)
        task.assignee_user_id = body.assignee_user_id
    if "due_date" in fields:
        task.due_date = body.due_date
    db.flush()
    return _task_with_name(db, task)


def delete_task(db: AppSession, ctx: TenantContext, task_id: UUID) -> None:
    task = _task(db, ctx, task_id)
    _editable_event(db, ctx, task.event_id)
    db.delete(task)
    db.flush()


# --- Para hacer hoy (dashboard) ------------------------------------------------------------

CONFIRM_HORIZON_DAYS = 7  # proveedores sin confirmar para eventos de la próxima semana
_ACTIVE_EVENT = (EventStatus.APPROVED, EventStatus.IN_PRODUCTION, EventStatus.COMPLETED)


class PendingKind(StrEnum):
    TASKS_OVERDUE = "TASKS_OVERDUE"  # tareas sin hacer con fecha anterior a hoy
    TASKS_TODAY = "TASKS_TODAY"
    TO_CONFIRM = "TO_CONFIRM"  # proveedores cotizados, el evento es en los próximos días
    TO_PAY = "TO_PAY"  # factura cargada, sin pagar


@dataclass(frozen=True)
class Pending:
    kind: PendingKind
    event_id: UUID
    event_number: int
    event_name: str
    count: int
    date: date | None  # vencimiento más viejo (tareas) o fecha del evento


def pending_operations(db: AppSession, ctx: TenantContext, today: date) -> list[Pending]:
    """Lo operativo que hay que resolver, agrupado por evento y ordenado por urgencia."""
    org = ctx.organization_id
    live = (
        Event.organization_id == org,
        Event.deleted_at.is_(None),
        Event.status.in_([s.value for s in _ACTIVE_EVENT]),
    )
    out: list[Pending] = []

    overdue = ProductionTask.due_date < today
    tasks = db.execute(
        select(
            Event.id,
            Event.number,
            Event.name,
            func.count().filter(overdue),
            func.min(ProductionTask.due_date).filter(overdue),
            func.count().filter(ProductionTask.due_date == today),
        )
        .join(Event, Event.id == ProductionTask.event_id)
        .where(
            *live,
            ProductionTask.organization_id == org,
            ProductionTask.status != TaskStatus.DONE.value,
            ProductionTask.due_date <= today,
        )
        .group_by(Event.id, Event.number, Event.name)
    ).all()
    for event_id, number, name, late, oldest, due_today in tasks:
        if late:
            out.append(Pending(PendingKind.TASKS_OVERDUE, event_id, number, name, late, oldest))
        if due_today:
            out.append(Pending(PendingKind.TASKS_TODAY, event_id, number, name, due_today, today))

    suppliers = db.execute(
        select(
            Event.id, Event.number, Event.name, Event.start_date, EventSupplier.status, func.count()
        )
        .join(Event, Event.id == EventSupplier.event_id)
        .where(
            *live,
            EventSupplier.organization_id == org,
            EventSupplier.supplier_id.is_not(None),  # lo propio no se confirma ni se paga
            or_(
                EventSupplier.status == HireStatus.INVOICED.value,
                and_(
                    EventSupplier.status == HireStatus.TO_HIRE.value,
                    Event.start_date >= today,
                    Event.start_date <= today + timedelta(days=CONFIRM_HORIZON_DAYS),
                ),
            ),
        )
        .group_by(Event.id, Event.number, Event.name, Event.start_date, EventSupplier.status)
    ).all()
    for event_id, number, name, start, status, count in suppliers:
        kind = PendingKind.TO_PAY if status == HireStatus.INVOICED else PendingKind.TO_CONFIRM
        out.append(Pending(kind, event_id, number, name, count, start))

    order = list(PendingKind)
    return sorted(out, key=lambda p: (order.index(p.kind), p.date or date.max, p.event_number))
