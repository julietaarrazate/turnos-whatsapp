"""Métricas comerciales para el dashboard (PRODUCT_SPEC §8). Solo lectura.

Definiciones exactas (para que nadie discuta qué es "aceptado este mes"):
- Enviado: venta neta de la última propuesta enviada por presupuesto con `sent_at` en el período.
- Aceptado: venta neta de las propuestas aceptadas (online o manual) con `decided_at` en el período.
- En negociación: venta neta de la última propuesta activa (enviada o vista, sin decidir y sin
  vencer) de cada presupuesto. Es una foto de hoy, no del período.
- Margen promedio: Σ ganancia / Σ venta neta de lo aceptado (ponderado por venta).
- Conversión: aceptadas / (aceptadas + rechazadas + vencidas) sobre las decisiones de la ventana.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.core.db import AppSession
from app.core.security import utcnow
from app.modules.auth import TenantContext
from app.modules.budgets import Budget, BudgetVersion
from app.modules.catalog import today_ar
from app.modules.events import Event, EventStatus
from app.modules.identity import Organization
from app.modules.proposals.models import ACTIVE, Proposal, ProposalStatus
from app.modules.proposals.pipeline import FollowUp, _effective, _follow_up


@dataclass
class Amount:
    count: int = 0
    amount: Decimal = Decimal("0.00")

    def add(self, value: Decimal) -> None:
        self.count += 1
        self.amount += value


@dataclass
class CommercialMetrics:
    sent: Amount = field(default_factory=Amount)
    accepted: Amount = field(default_factory=Amount)
    accepted_profit: Decimal = Decimal("0.00")
    in_negotiation: Amount = field(default_factory=Amount)
    won: Amount = field(default_factory=Amount)  # ventana de conversión
    lost: Amount = field(default_factory=Amount)  # rechazadas + vencidas
    follow_ups: dict[FollowUp, int] = field(default_factory=lambda: dict.fromkeys(FollowUp, 0))


@dataclass(frozen=True)
class _Row:
    proposal: Proposal
    sale_net: Decimal
    profit: Decimal
    event_status: EventStatus


def _in(moment: datetime | None, start: datetime, end: datetime) -> bool:
    return moment is not None and start <= moment < end


def commercial_metrics(
    db: AppSession,
    ctx: TenantContext,
    *,
    start: datetime,
    end: datetime,
    window_start: datetime,
    own_only: bool,
) -> CommercialMetrics:
    """`[start, end)` es el período; `[window_start, ahora)` la ventana de conversión.
    Con `own_only`, solo los presupuestos que creó el usuario (QUOTER ve lo propio)."""
    query = (
        select(Proposal, BudgetVersion.sale_net, BudgetVersion.profit, Event.status)
        .join(BudgetVersion, BudgetVersion.id == Proposal.budget_version_id)
        .join(Budget, Budget.id == Proposal.budget_id)
        .join(Event, Event.id == Budget.event_id)
        .where(
            Proposal.organization_id == ctx.organization_id,
            Proposal.status != ProposalStatus.REVOKED,
            Event.deleted_at.is_(None),
        )
        .order_by(Proposal.sent_at.desc(), Proposal.number.desc())
    )
    if own_only:
        query = query.where(Budget.created_by == ctx.user_id)
    by_budget: dict[UUID, list[_Row]] = defaultdict(list)
    for proposal, sale_net, profit, event_status in db.execute(query).all():
        by_budget[proposal.budget_id].append(
            _Row(proposal, sale_net, profit, EventStatus(event_status))
        )

    org = db.get(Organization, ctx.organization_id)
    days = org.follow_up_days if org else 5
    now = utcnow()
    window_from: date = window_start.date()
    today = today_ar()
    metrics = CommercialMetrics()
    for rows in by_budget.values():
        latest = rows[0]
        sent_in_period = next((r for r in rows if _in(r.proposal.sent_at, start, end)), None)
        if sent_in_period is not None:
            metrics.sent.add(sent_in_period.sale_net)
        if _effective(latest.proposal) in ACTIVE:
            metrics.in_negotiation.add(latest.sale_net)
        follow_up = _follow_up(latest.event_status, latest.proposal, now, days)
        if follow_up is not None:
            metrics.follow_ups[follow_up] += 1
        for row in rows:
            proposal = row.proposal
            status = _effective(proposal)
            if status is ProposalStatus.ACCEPTED:
                if _in(proposal.decided_at, start, end):
                    metrics.accepted.add(row.sale_net)
                    metrics.accepted_profit += row.profit
                if _in(proposal.decided_at, window_start, now):
                    metrics.won.add(row.sale_net)
            elif (
                status is ProposalStatus.REJECTED and _in(proposal.decided_at, window_start, now)
            ) or (status is ProposalStatus.EXPIRED and window_from <= proposal.valid_until < today):
                metrics.lost.add(row.sale_net)
    return metrics
