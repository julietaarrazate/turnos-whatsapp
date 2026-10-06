"""Pipeline de presupuestos (B-12) y "para seguir" (PRODUCT_SPEC §8).

El estado comercial de cada presupuesto se deriva de sus propuestas y del evento; no se guarda.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select

from app.core.db import AppSession
from app.core.security import utcnow
from app.modules.auth import TenantContext
from app.modules.budgets import BudgetSummary, list_budgets
from app.modules.catalog import today_ar
from app.modules.events import EventStatus
from app.modules.identity import Organization
from app.modules.proposals.models import ACTIVE, Proposal, ProposalStatus

# Para la piloto alcanza con traer todo: el filtro por estado derivado se hace en memoria.
PIPELINE_LIMIT = 300
VIEWED_NO_ANSWER = timedelta(hours=48)
_CLOSED_EVENT = {EventStatus.LOST, EventStatus.CANCELLED}
_OPEN_EVENT = {EventStatus.SENT, EventStatus.NEGOTIATION}


class PipelineStatus(StrEnum):
    DRAFT = "DRAFT"  # todavía no se envió
    SENT = "SENT"
    VIEWED = "VIEWED"
    NEGOTIATION = "NEGOTIATION"  # reenvíos, rechazo o vencida: hay que volver a proponer
    ACCEPTED = "ACCEPTED"
    LOST = "LOST"


class FollowUp(StrEnum):
    EXPIRING = "EXPIRING"  # vence en menos de 48 h
    VIEWED_NO_ANSWER = "VIEWED_NO_ANSWER"  # la vio hace más de 48 h y no respondió
    NO_RESPONSE = "NO_RESPONSE"  # enviada hace más de N días, sin decisión


class LastProposal(BaseModel):
    id: UUID
    number: int
    status: ProposalStatus
    sent_at: datetime
    valid_until: str
    first_viewed_at: datetime | None
    view_count: int


class PipelineItem(BudgetSummary):
    pipeline_status: PipelineStatus
    follow_up: FollowUp | None
    proposals_sent: int
    last_proposal: LastProposal | None


class Pipeline(BaseModel):
    items: list[PipelineItem]
    counts: dict[PipelineStatus, int]
    follow_up: int
    follow_up_days: int
    truncated: bool


def _effective(proposal: Proposal) -> ProposalStatus:
    status = ProposalStatus(proposal.status)
    if status in ACTIVE and proposal.valid_until < today_ar():
        return ProposalStatus.EXPIRED
    return status


def _status(event: EventStatus, proposals: list[Proposal]) -> PipelineStatus:
    if any(p.status == ProposalStatus.ACCEPTED for p in proposals):
        return PipelineStatus.ACCEPTED
    if event in _CLOSED_EVENT:
        return PipelineStatus.LOST
    if not proposals:
        return PipelineStatus.DRAFT
    latest = _effective(proposals[0])
    if latest in ACTIVE and len(proposals) == 1:
        return PipelineStatus(latest.value)
    return PipelineStatus.NEGOTIATION


def _follow_up(
    event: EventStatus, latest: Proposal | None, now: datetime, days: int
) -> FollowUp | None:
    if latest is None or event not in _OPEN_EVENT or _effective(latest) not in ACTIVE:
        return None
    if latest.valid_until <= today_ar() + timedelta(days=1):
        return FollowUp.EXPIRING
    if latest.first_viewed_at and now - latest.first_viewed_at > VIEWED_NO_ANSWER:
        return FollowUp.VIEWED_NO_ANSWER
    if now - latest.sent_at > timedelta(days=days):
        return FollowUp.NO_RESPONSE
    return None


def pipeline(
    db: AppSession,
    ctx: TenantContext,
    *,
    q: str | None,
    status: PipelineStatus | None,
    follow_up_only: bool,
) -> Pipeline:
    page = list_budgets(db, ctx, q=q, event_id=None, cursor=None, limit=PIPELINE_LIMIT)
    by_budget: dict[UUID, list[Proposal]] = defaultdict(list)
    if page.items:
        rows = db.execute(
            select(Proposal)
            .where(
                Proposal.organization_id == ctx.organization_id,
                Proposal.budget_id.in_([b.id for b in page.items]),
            )
            .order_by(Proposal.sent_at.desc(), Proposal.number.desc())
        ).scalars()
        for proposal in rows:
            by_budget[proposal.budget_id].append(proposal)

    org = db.get(Organization, ctx.organization_id)
    days = org.follow_up_days if org else 5
    now = utcnow()
    items: list[PipelineItem] = []
    for budget in page.items:
        proposals = by_budget[budget.id]
        latest = proposals[0] if proposals else None
        items.append(
            PipelineItem(
                **budget.model_dump(),
                pipeline_status=_status(budget.event_status, proposals),
                follow_up=_follow_up(budget.event_status, latest, now, days),
                proposals_sent=len(proposals),
                last_proposal=LastProposal(
                    id=latest.id,
                    number=latest.number,
                    status=_effective(latest),
                    sent_at=latest.sent_at,
                    valid_until=latest.valid_until.isoformat(),
                    first_viewed_at=latest.first_viewed_at,
                    view_count=latest.view_count,
                )
                if latest
                else None,
            )
        )
    counts = {s: sum(1 for i in items if i.pipeline_status is s) for s in PipelineStatus}
    pending = sum(1 for i in items if i.follow_up is not None)
    if status is not None:
        items = [i for i in items if i.pipeline_status is status]
    if follow_up_only:
        items = [i for i in items if i.follow_up is not None]
    return Pipeline(
        items=items,
        counts=counts,
        follow_up=pending,
        follow_up_days=days,
        truncated=page.next_cursor is not None,
    )
