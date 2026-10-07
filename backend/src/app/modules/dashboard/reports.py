"""Reportes (A-02): rentabilidad por evento, cliente y período, e historial del cliente.

Entra todo evento con presupuesto aceptado y fecha en el rango. La ganancia real solo se
calcula para eventos con gastos cargados y es "parcial" si el evento no está cerrado
(PRODUCT_SPEC §8).
"""

import csv
import io
from collections import OrderedDict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, select

from app.core.db import AppSession
from app.core.errors import AppError
from app.modules.auth import TenantContext
from app.modules.budgets import Budget, versions_totals
from app.modules.clients import Client, get_active
from app.modules.dashboard.schemas import ClientHistoryOut, ReportOut, ReportRow
from app.modules.events import Event, EventStatus
from app.modules.finance import actual_costs, deviation
from app.modules.pricing import client_rule

RATE = Decimal("0.000001")
ZERO = Decimal("0.00")
MAX_EVENTS = 2000


class ReportGroup(StrEnum):
    EVENT = "event"
    CLIENT = "client"
    MONTH = "month"


def _ratio(part: Decimal, whole: Decimal) -> Decimal | None:
    return (part / whole).quantize(RATE, rounding=ROUND_HALF_UP) if whole else None


class _Acc:
    def __init__(self, key: str, label: str) -> None:
        self.key, self.label = key, label
        self.events = 0
        self.sale_net = ZERO
        self.estimated_cost = ZERO
        self.estimated_profit = ZERO
        self.with_costs = 0
        self.sale_with_costs = ZERO
        self.budgeted_with_costs = ZERO
        self.actual_cost = ZERO
        self.actual_profit = ZERO
        self.partial = False

    def row(self) -> ReportRow:
        _, cost_delta_rate = deviation(self.budgeted_with_costs, self.actual_cost)
        return ReportRow(
            key=self.key,
            label=self.label,
            events=self.events,
            sale_net=self.sale_net,
            estimated_cost=self.estimated_cost,
            estimated_profit=self.estimated_profit,
            estimated_margin=_ratio(self.estimated_profit, self.sale_net),
            events_with_costs=self.with_costs,
            actual_cost=self.actual_cost if self.with_costs else None,
            actual_profit=self.actual_profit if self.with_costs else None,
            actual_margin=_ratio(self.actual_profit, self.sale_with_costs)
            if self.with_costs
            else None,
            cost_delta_rate=cost_delta_rate if self.with_costs else None,
            partial=self.partial,
        )


def profitability_report(
    db: AppSession,
    ctx: TenantContext,
    *,
    date_from: date,
    date_to: date,
    group: ReportGroup,
) -> ReportOut:
    if date_to < date_from:
        raise AppError(422, "invalid_range", "La fecha final es anterior a la inicial")
    rows = db.execute(
        select(Event, Client.name)
        .join(Client, Client.id == Event.client_id)
        .where(
            Event.organization_id == ctx.organization_id,
            Event.deleted_at.is_(None),
            Event.accepted_budget_version_id.is_not(None),
            Event.start_date >= date_from,
            Event.start_date <= date_to,
        )
        .order_by(Event.start_date, Event.number)
        .limit(MAX_EVENTS)
    ).all()
    events = [event for event, _ in rows]
    totals = versions_totals(
        db,
        ctx.organization_id,
        [e.accepted_budget_version_id for e in events if e.accepted_budget_version_id],
    )
    costs = actual_costs(db, ctx.organization_id, [e.id for e in events])
    groups: OrderedDict[str, _Acc] = OrderedDict()
    overall = _Acc("total", "Total")
    for event, client_name in rows:
        version = totals.get(event.accepted_budget_version_id)  # type: ignore[arg-type]
        if version is None or event.start_date is None:
            continue
        if group is ReportGroup.EVENT:
            key, label = str(event.id), f"#{event.number} · {event.name} ({client_name})"
        elif group is ReportGroup.CLIENT:
            key, label = str(event.client_id), client_name
        else:
            key = label = f"{event.start_date:%Y-%m}"
        actual = costs.get(event.id)
        for acc in (groups.setdefault(key, _Acc(key, label)), overall):
            acc.events += 1
            acc.sale_net += version.sale_net
            acc.estimated_cost += version.cost_direct
            acc.estimated_profit += version.profit
            if actual is not None:
                actual_cost, _ = actual
                acc.with_costs += 1
                acc.sale_with_costs += version.sale_net
                acc.budgeted_with_costs += version.cost_direct
                acc.actual_cost += actual_cost
                acc.actual_profit += version.sale_net - actual_cost - version.sale_charges
            if EventStatus(event.status) is not EventStatus.CLOSED:
                acc.partial = True
    return ReportOut(
        date_from=date_from,
        date_to=date_to,
        group=group.value,
        rows=[acc.row() for acc in groups.values()],
        total=overall.row(),
        truncated=len(rows) == MAX_EVENTS,
    )


def _money(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.2f}".replace(".", ",")


def _pct(value: Decimal | None) -> str:
    return "" if value is None else f"{value * 100:.2f}".replace(".", ",")


def report_csv(report: ReportOut) -> str:
    """CSV para Excel en español: separador ";" y coma decimal, con BOM para los acentos."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(
        [
            "Grupo",
            "Eventos",
            "Venta neta",
            "Costo estimado",
            "Ganancia estimada",
            "Margen estimado %",
            "Eventos con gastos",
            "Costo real",
            "Ganancia real",
            "Margen real %",
            "Desvío de costo %",
            "Parcial",
        ]
    )
    for row in [*report.rows, report.total]:
        writer.writerow(
            [
                row.label,
                row.events,
                _money(row.sale_net),
                _money(row.estimated_cost),
                _money(row.estimated_profit),
                _pct(row.estimated_margin),
                row.events_with_costs,
                _money(row.actual_cost),
                _money(row.actual_profit),
                _pct(row.actual_margin),
                _pct(row.cost_delta_rate),
                "sí" if row.partial else "no",
            ]
        )
    return "﻿" + out.getvalue()


def client_history(
    db: AppSession, ctx: TenantContext, client_id: UUID, *, margins: bool
) -> ClientHistoryOut:
    """Historial comercial del cliente, calculado (PRODUCT_SPEC §4.2)."""
    client = get_active(db, ctx, client_id)
    events = list(
        db.execute(
            select(Event).where(
                Event.organization_id == ctx.organization_id,
                Event.client_id == client.id,
                Event.deleted_at.is_(None),
            )
        ).scalars()
    )
    budgets = db.execute(
        select(func.count())
        .select_from(Budget)
        .where(
            Budget.organization_id == ctx.organization_id,
            Budget.event_id.in_([e.id for e in events]),
        )
    ).scalar_one()
    accepted_events = [e for e in events if e.accepted_budget_version_id]
    lost = sum(
        1 for e in events if e.status == EventStatus.LOST and not e.accepted_budget_version_id
    )
    totals = versions_totals(
        db,
        ctx.organization_id,
        [e.accepted_budget_version_id for e in accepted_events],  # type: ignore[misc]
    )
    costs = actual_costs(db, ctx.organization_id, [e.id for e in accepted_events])
    billed = sum((t.sale_net for t in totals.values()), ZERO)
    profit = sum((t.profit for t in totals.values()), ZERO)
    real_sale = real_profit = ZERO
    for event in accepted_events:
        version = totals.get(event.accepted_budget_version_id)  # type: ignore[arg-type]
        if version is not None and event.id in costs:
            real_sale += version.sale_net
            real_profit += version.sale_net - costs[event.id][0] - version.sale_charges
    rule = client_rule(db, ctx, client.id) if margins else None
    decided = len(accepted_events) + lost
    return ClientHistoryOut(
        client_id=client.id,
        budgets=budgets,
        events=len(events),
        accepted=len(accepted_events),
        lost=lost,
        conversion=_ratio(Decimal(len(accepted_events)), Decimal(decided)),
        billed=billed,
        estimated_margin=_ratio(profit, billed) if margins else None,
        actual_margin=_ratio(real_profit, real_sale) if margins else None,
        preferential_markup=rule.value if rule else None,
        preferential_mode=rule.mode.value if rule else None,
    )
