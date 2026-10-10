"""Gastos reales del evento y presupuestado vs real (O-04, D-21, journey J6).

El gasto se compara con la versión aceptada (la baseline) por línea cuando está vinculado y,
si no, queda como "No presupuestado" en su categoría. El monto efectivo se calcula como el
costo de una línea en el motor (L1–L2), así lo real y lo presupuestado son comparables.
"""

from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from fastapi import Response
from sqlalchemy import func, select

from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.core.permissions import Permission
from app.domain.pricing import LineInput, effective_unit_cost
from app.modules.audit import record
from app.modules.auth import TenantContext
from app.modules.budgets import BaselineLine, baseline_lines, version_totals
from app.modules.catalog import category_info, supplier_name, today_ar
from app.modules.documents import (
    DocumentKind,
    documents_by_id,
    file_response,
    get_document,
    uploads_enabled,
)
from app.modules.events import Event, EventStatus, get_event
from app.modules.finance.models import Expense, ExpenseCurrency
from app.modules.finance.profitability import Result, deviation, result
from app.modules.finance.schemas import (
    ComparisonRow,
    ExpenseIn,
    ExpenseOut,
    ExpensesOut,
    ExpenseUpdate,
    LineOption,
    ProfitabilityOut,
    ResultOut,
)
from app.modules.identity import User
from app.modules.pricing import latest_fx_rate, pricing_context

CENT = Decimal("0.01")
RATE = Decimal("0.000001")
# Se cargan gastos desde que el evento está aprobado hasta que se cierra; también si se canceló
# (los costos de la cancelación). Cerrado, son de solo lectura (DOMAIN_MODEL §3.1).
_OPEN = {
    EventStatus.APPROVED,
    EventStatus.IN_PRODUCTION,
    EventStatus.COMPLETED,
    EventStatus.CANCELLED,
}
_FIELDS = (
    "description",
    "amount",
    "currency",
    "amount_includes_iva",
    "iva_rate",
    "fx_rate",
    "expense_date",
    "line_key",
    "supplier_id",
    "category_id",
    "receipt_document_id",
)


def _audit(
    db: AppSession, ctx: TenantContext, action: str, expense: Expense, **changes: Any
) -> None:
    record(
        db,
        organization_id=ctx.organization_id,
        action=action,
        entity_type="expense",
        entity_id=expense.id,
        actor_user_id=ctx.user_id,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
        **changes,
    )


def _snapshot(expense: Expense) -> dict[str, Any]:
    return {
        "event_id": str(expense.event_id),
        "description": expense.description,
        "amount": str(expense.amount),
        "currency": expense.currency,
        "amount_base": str(expense.amount_base),
        "line_key": str(expense.line_key) if expense.line_key else None,
        "receipt_document_id": (
            str(expense.receipt_document_id) if expense.receipt_document_id else None
        ),
    }


def _baseline(db: AppSession, ctx: TenantContext, event: Event) -> list[BaselineLine]:
    if event.accepted_budget_version_id is None:
        return []
    return baseline_lines(db, ctx.organization_id, event.accepted_budget_version_id)


def _editable_event(db: AppSession, ctx: TenantContext, event_id: UUID) -> Event:
    event = get_event(db, ctx, event_id)
    status = EventStatus(event.status)
    if status is EventStatus.CLOSED:
        raise AppError(409, "event_locked", "El evento está cerrado: no se cargan más gastos")
    if status not in _OPEN:
        raise AppError(
            409, "event_not_approved", "Los gastos se cargan cuando el evento está aprobado"
        )
    return event


def _amount_base(db: AppSession, ctx: TenantContext, event: Event, expense: Expense) -> Decimal:
    """L1–L2: un RI computa el costo sin IVA (es crédito fiscal); los demás, con IVA."""
    tax = pricing_context(db, ctx, event.client_id).tax_condition
    item = LineInput(
        key="expense",
        quantity=Decimal(1),
        unit_cost=expense.amount,
        cost_includes_iva=expense.amount_includes_iva,
        cost_iva_rate=expense.iva_rate,
    )
    effective = effective_unit_cost(item, tax) * expense.fx_rate
    return effective.quantize(CENT, rounding=ROUND_HALF_UP)


def _apply(
    db: AppSession,
    ctx: TenantContext,
    event: Event,
    expense: Expense,
    *,
    explicit: set[str],
) -> None:
    """Completa con la línea (proveedor, categoría), valida y recalcula el monto efectivo."""
    if expense.line_key is not None:
        line = next(
            (ln for ln in _baseline(db, ctx, event) if ln.line_key == expense.line_key), None
        )
        if line is None:
            raise AppError(
                422, "expense_line_not_found", "Esa línea no está en el presupuesto aprobado"
            )
        if "supplier_id" not in explicit and expense.supplier_id is None:
            expense.supplier_id = line.supplier_id
        if "category_id" not in explicit and expense.category_id is None:
            expense.category_id = line.category_id
    if expense.line_key is None and expense.category_id is None:
        raise AppError(
            422,
            "expense_needs_line_or_category",
            "Elegí la línea del presupuesto o, si no estaba presupuestado, una categoría",
        )
    if expense.supplier_id is not None:
        supplier_name(db, ctx, expense.supplier_id)  # 404 si es de otra organización
    if expense.category_id is not None:
        category_info(db, ctx, expense.category_id)
    if "receipt_document_id" in explicit and expense.receipt_document_id is not None:
        _check_receipt(db, ctx, expense, expense.receipt_document_id)
    # En dólares: el tipo de cambio indicado o, si no, el último cargado. Al editar otra cosa,
    # se conserva el que tenía.
    keeps_rate = expense.id is not None and not {"fx_rate", "currency"} & explicit
    if expense.currency == ExpenseCurrency.ARS:
        expense.fx_rate = Decimal(1)
    elif expense.fx_rate is None or not (keeps_rate or "fx_rate" in explicit):
        fx = latest_fx_rate(db, ctx, expense.currency)
        if fx is None:
            raise AppError(
                422, "fx_rate_required", "Cargá el tipo de cambio del dólar o indicalo en el gasto"
            )
        expense.fx_rate = fx.rate
    # Con la escala de las columnas, así la respuesta es igual antes y después de recargar.
    expense.amount = expense.amount.quantize(CENT)
    expense.iva_rate = expense.iva_rate.quantize(Decimal("0.0001"))
    expense.fx_rate = expense.fx_rate.quantize(RATE)
    expense.amount_base = _amount_base(db, ctx, event, expense)


def _check_receipt(db: AppSession, ctx: TenantContext, expense: Expense, document_id: UUID) -> None:
    """El comprobante es de la organización, es un comprobante y no está en otro gasto."""
    get_document(db, ctx.organization_id, document_id, DocumentKind.RECEIPT)
    query = select(Expense.id).where(
        Expense.organization_id == ctx.organization_id, Expense.receipt_document_id == document_id
    )
    if expense.id is not None:
        query = query.where(Expense.id != expense.id)
    if db.execute(query).first() is not None:
        raise AppError(409, "document_in_use", "Ese comprobante ya está en otro gasto")


def _expense(db: AppSession, ctx: TenantContext, expense_id: UUID) -> Expense:
    expense = db.execute(
        select(Expense).where(
            Expense.id == expense_id, Expense.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if expense is None:
        raise not_found()
    return expense


def _row(
    key: str, label: str, section: str | None, budgeted: Decimal | None, actual: Decimal
) -> ComparisonRow:
    if budgeted is None:
        delta, delta_rate = None, None
    else:
        delta, delta_rate = deviation(budgeted, actual)
    return ComparisonRow(
        key=key,
        label=label,
        section=section,
        budgeted=budgeted,
        actual=actual,
        delta=delta,
        delta_rate=delta_rate,
    )


def _by_line(
    lines: list[BaselineLine], expenses: list[Expense], categories: dict[UUID, str]
) -> list[ComparisonRow]:
    """Por línea cuando el gasto está vinculado; lo demás, "No presupuestado" por categoría."""
    actual_by_line: dict[UUID, Decimal] = {}
    unbudgeted: OrderedDict[UUID | None, Decimal] = OrderedDict()
    for expense in expenses:
        if expense.line_key is not None:
            actual_by_line[expense.line_key] = (
                actual_by_line.get(expense.line_key, Decimal(0)) + expense.amount_base
            )
        else:
            unbudgeted[expense.category_id] = (
                unbudgeted.get(expense.category_id, Decimal(0)) + expense.amount_base
            )
    rows = []
    for line in lines:
        actual = actual_by_line.get(line.line_key, Decimal(0))
        if line.cost_total == 0 and actual == 0:
            continue
        rows.append(
            _row(str(line.line_key), line.name, line.section_title or None, line.cost_total, actual)
        )
    for category_id, actual in unbudgeted.items():
        name = categories.get(category_id, _NO_CATEGORY) if category_id else _NO_CATEGORY
        rows.append(
            _row(f"unbudgeted:{category_id}", f"No presupuestado · {name}", None, None, actual)
        )
    return rows


_NO_CATEGORY = "Sin categoría"
_ZERO = Decimal("0.00")
_NO_SUPPLIER = "Sin proveedor"


def _grouped(
    budgeted: list[tuple[UUID | None, str | None, Decimal]],
    actual: list[tuple[UUID | None, str | None, Decimal]],
    empty_label: str,
) -> list[ComparisonRow]:
    """Presupuestado vs real agrupado (por categoría o por proveedor). Un grupo sin nada
    presupuestado aparece con presupuesto 0: todo su real es desvío."""
    labels: OrderedDict[UUID | None, str] = OrderedDict()
    planned: dict[UUID | None, Decimal] = {}
    real: dict[UUID | None, Decimal] = {}
    for key, label, amount in budgeted:
        labels.setdefault(key, label or empty_label)
        planned[key] = planned.get(key, _ZERO) + amount
    for key, label, amount in actual:
        labels.setdefault(key, label or empty_label)
        real[key] = real.get(key, _ZERO) + amount
    rows = [
        _row(
            str(key) if key else "none",
            label,
            None,
            planned.get(key, _ZERO),
            real.get(key, _ZERO),
        )
        for key, label in labels.items()
        if planned.get(key) or real.get(key)
    ]
    return sorted(rows, key=lambda r: r.key == "none")  # "Sin …" al final


class _Loaded:
    """Lo que hace falta para comparar: baseline, gastos y nombres."""

    def __init__(self, db: AppSession, ctx: TenantContext, event: Event) -> None:
        self.event = event
        self.lines = _baseline(db, ctx, event)
        self.expenses = list(
            db.execute(
                select(Expense)
                .where(Expense.event_id == event.id, Expense.organization_id == ctx.organization_id)
                .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            ).scalars()
        )
        self.categories = {
            cid: category_info(db, ctx, cid)[0].name
            for cid in {e.category_id for e in self.expenses if e.category_id}
        }
        self.suppliers = {
            sid: supplier_name(db, ctx, sid)
            for sid in {e.supplier_id for e in self.expenses if e.supplier_id}
        }

    @property
    def budgeted_total(self) -> Decimal:
        return sum((line.cost_total for line in self.lines), Decimal(0))

    @property
    def actual_total(self) -> Decimal:
        return sum((e.amount_base for e in self.expenses), Decimal(0))

    def by_category(self) -> list[ComparisonRow]:
        return _grouped(
            [(ln.category_id, ln.category_name, ln.cost_total) for ln in self.lines],
            [
                (
                    e.category_id,
                    self.categories.get(e.category_id) if e.category_id else None,
                    e.amount_base,
                )
                for e in self.expenses
            ],
            _NO_CATEGORY,
        )

    def by_supplier(self) -> list[ComparisonRow]:
        return _grouped(
            [(ln.supplier_id, ln.supplier_name, ln.cost_total) for ln in self.lines],
            [
                (
                    e.supplier_id,
                    self.suppliers.get(e.supplier_id) if e.supplier_id else None,
                    e.amount_base,
                )
                for e in self.expenses
            ],
            _NO_SUPPLIER,
        )


def list_expenses(db: AppSession, ctx: TenantContext, event_id: UUID) -> ExpensesOut:
    data = _Loaded(db, ctx, get_event(db, ctx, event_id))
    event, lines, expenses = data.event, data.lines, data.expenses
    by_key = {line.line_key: line for line in lines}
    users = {
        user.id: user.name
        for user in db.execute(
            select(User).where(User.id.in_({e.created_by for e in expenses}))
        ).scalars()
    }
    receipts = documents_by_id(
        db, ctx.organization_id, {e.receipt_document_id for e in expenses if e.receipt_document_id}
    )
    _, delta_rate = deviation(data.budgeted_total, data.actual_total)
    status = EventStatus(event.status)
    return ExpensesOut(
        event_id=event.id,
        editable=ctx.can(Permission.EXPENSES_EDIT) and status in _OPEN,
        receipts_enabled=uploads_enabled(),
        has_baseline=bool(lines),
        items=[
            ExpenseOut(
                id=e.id,
                event_id=e.event_id,
                description=e.description,
                amount=e.amount,
                currency=ExpenseCurrency(e.currency),
                amount_includes_iva=e.amount_includes_iva,
                iva_rate=e.iva_rate,
                fx_rate=e.fx_rate,
                amount_base=e.amount_base,
                expense_date=e.expense_date,
                line_key=e.line_key,
                line_name=by_key[e.line_key].name if e.line_key in by_key else None,
                supplier_id=e.supplier_id,
                supplier_name=data.suppliers.get(e.supplier_id) if e.supplier_id else None,
                category_id=e.category_id,
                category_name=data.categories.get(e.category_id) if e.category_id else None,
                receipt=receipts.get(e.receipt_document_id) if e.receipt_document_id else None,
                created_by_name=users.get(e.created_by),
                created_at=e.created_at,
            )
            for e in expenses
        ],
        lines=[
            LineOption(
                line_key=line.line_key,
                name=line.name,
                section=line.section_title,
                supplier_id=line.supplier_id,
                supplier_name=line.supplier_name,
                category_id=line.category_id,
                category_name=line.category_name,
                budgeted=line.cost_total,
            )
            for line in lines
        ],
        comparison=_by_line(lines, expenses, data.categories),
        by_category=data.by_category(),
        by_supplier=data.by_supplier(),
        budgeted_total=data.budgeted_total,
        actual_total=data.actual_total,
        delta_rate=delta_rate,
    )


def _result_out(value: Result) -> ResultOut:
    return ResultOut(
        sale_net=value.sale_net,
        cost=value.cost,
        sale_charges=value.sale_charges,
        profit=value.profit,
        margin=value.margin,
    )


def get_profitability(db: AppSession, ctx: TenantContext, event_id: UUID) -> ProfitabilityOut:
    """O-06: estimado (la versión aceptada) vs real (los gastos). Hasta que el evento se cierra,
    lo real es parcial; cerrado, no cambia más (versión congelada y gastos de solo lectura)."""
    event = get_event(db, ctx, event_id)
    totals = (
        version_totals(db, ctx.organization_id, event.accepted_budget_version_id)
        if event.accepted_budget_version_id
        else None
    )
    status = EventStatus(event.status)
    if totals is None:
        return ProfitabilityOut(
            event_id=event.id,
            status=status,
            final=False,
            estimated=None,
            actual=None,
            cost_delta=None,
            cost_delta_rate=None,
            expenses_count=0,
        )
    data = _Loaded(db, ctx, event)
    estimated = result(totals.sale_net, totals.cost_direct, totals.sale_charges)
    actual = result(totals.sale_net, data.actual_total, totals.sale_charges)
    delta, delta_rate = deviation(totals.cost_direct, data.actual_total)
    return ProfitabilityOut(
        event_id=event.id,
        status=status,
        final=status is EventStatus.CLOSED,
        estimated=_result_out(estimated),
        actual=_result_out(actual),
        cost_delta=delta,
        cost_delta_rate=delta_rate,
        expenses_count=len(data.expenses),
    )


def create_expense(
    db: AppSession, ctx: TenantContext, event_id: UUID, body: ExpenseIn
) -> ExpensesOut:
    event = _editable_event(db, ctx, event_id)
    expense = Expense(
        organization_id=ctx.organization_id,
        event_id=event.id,
        created_by=ctx.user_id,
        **body.model_dump(include=set(_FIELDS) - {"expense_date", "currency"}),
        currency=body.currency.value,
        expense_date=body.expense_date or today_ar(),
    )
    expense.description = expense.description.strip()
    _apply(db, ctx, event, expense, explicit=body.model_fields_set)
    db.add(expense)
    db.flush()
    _audit(db, ctx, "expense.created", expense, after=_snapshot(expense))
    return list_expenses(db, ctx, event.id)


def update_expense(
    db: AppSession, ctx: TenantContext, expense_id: UUID, body: ExpenseUpdate
) -> ExpensesOut:
    expense = _expense(db, ctx, expense_id)
    event = _editable_event(db, ctx, expense.event_id)
    before = _snapshot(expense)
    nullable = {"line_key", "supplier_id", "category_id", "fx_rate", "receipt_document_id"}
    for field in body.model_fields_set & set(_FIELDS):
        value = getattr(body, field)
        if value is None and field not in nullable:
            continue
        if field == "currency":
            value = value.value
        elif field == "description":
            value = value.strip()
        setattr(expense, field, value)
    _apply(db, ctx, event, expense, explicit=body.model_fields_set)
    db.flush()
    _audit(db, ctx, "expense.updated", expense, before=before, after=_snapshot(expense))
    return list_expenses(db, ctx, event.id)


def delete_expense(db: AppSession, ctx: TenantContext, expense_id: UUID) -> ExpensesOut:
    expense = _expense(db, ctx, expense_id)
    event = _editable_event(db, ctx, expense.event_id)
    _audit(db, ctx, "expense.deleted", expense, before=_snapshot(expense))
    db.delete(expense)
    db.flush()
    return list_expenses(db, ctx, event.id)


def receipt_file(db: AppSession, ctx: TenantContext, expense_id: UUID) -> Response:
    expense = _expense(db, ctx, expense_id)
    if expense.receipt_document_id is None:
        raise not_found("receipt_not_found", "El gasto no tiene comprobante")
    document = get_document(
        db, ctx.organization_id, expense.receipt_document_id, DocumentKind.RECEIPT
    )
    return file_response(document)


def actual_costs(
    db: AppSession, organization_id: UUID, event_ids: list[UUID]
) -> dict[UUID, tuple[Decimal, int]]:
    """Costo real (Σ monto efectivo) y cantidad de gastos por evento (reportes)."""
    if not event_ids:
        return {}
    rows = db.execute(
        select(Expense.event_id, func.sum(Expense.amount_base), func.count())
        .where(Expense.organization_id == organization_id, Expense.event_id.in_(event_ids))
        .group_by(Expense.event_id)
    ).all()
    return {event_id: (total, count) for event_id, total, count in rows}
