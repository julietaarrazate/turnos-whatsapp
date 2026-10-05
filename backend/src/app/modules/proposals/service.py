"""Propuestas: la versión congelada que se publica al cliente (DOMAIN_MODEL §2.7, §3.3)."""

import hashlib
import json
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.counters import next_number
from app.core.db import AppSession, DbContext, set_context
from app.core.errors import AppError, not_found
from app.core.security import new_token, token_hash, utcnow
from app.modules.audit import record
from app.modules.auth import ClientInfo, TenantContext
from app.modules.budgets import (
    DisplayMode,
    IvaDisplay,
    ensure_budget,
    freeze_for_proposal,
    public_snapshot,
    sendable_version,
)
from app.modules.catalog import today_ar
from app.modules.events import on_proposal_sent
from app.modules.identity import Organization
from app.modules.proposals.models import (
    ACTIVE,
    ActivityType,
    Proposal,
    ProposalActivity,
    ProposalStatus,
)
from app.modules.proposals.public_schemas import PublicProposal, PublicSnapshot
from app.modules.proposals.schemas import ProposalCreated, ProposalIn, ProposalOut

PUBLIC_PATH = "/p/"
# Los que arman la vista previa del link (WhatsApp, Telegram, Slack…) no son el cliente.
_PREVIEW_BOTS = (
    "facebookexternalhit",
    "whatsapp",
    "telegrambot",
    "slackbot",
    "twitterbot",
    "bot/",
    "crawler",
)


def _is_preview_bot(user_agent: str | None) -> bool:
    ua = (user_agent or "").lower()
    return any(marker in ua for marker in _PREVIEW_BOTS)


def _audit(
    db: AppSession,
    organization_id: UUID,
    actor: UUID | None,
    action: str,
    entity_id: UUID,
    **changes: Any,
) -> None:
    record(
        db,
        organization_id=organization_id,
        action=action,
        entity_type="proposal",
        entity_id=entity_id,
        actor_user_id=actor,
        **changes,
    )


def content_hash(snapshot: dict[str, Any]) -> str:
    """SHA-256 del JSON canónico: es la evidencia de qué vio (y aceptó) el cliente (I7)."""
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _activity(
    db: AppSession,
    proposal: Proposal,
    kind: ActivityType,
    client: ClientInfo | None = None,
    **payload: Any,
) -> None:
    db.add(
        ProposalActivity(
            organization_id=proposal.organization_id,
            proposal_id=proposal.id,
            type=kind.value,
            ip=client.ip if client else None,
            user_agent=(client.user_agent or "")[:500] if client else None,
            payload=payload or None,
        )
    )


def _effective_status(proposal: Proposal) -> ProposalStatus:
    """Una propuesta activa vencida se ve como EXPIRED aunque el cron todavía no haya pasado."""
    status = ProposalStatus(proposal.status)
    if status in ACTIVE and proposal.valid_until < today_ar():
        return ProposalStatus.EXPIRED
    return status


def _out(proposal: Proposal) -> ProposalOut:
    snapshot = proposal.public_snapshot
    return ProposalOut(
        id=proposal.id,
        number=proposal.number,
        budget_id=proposal.budget_id,
        version_no=snapshot["version_no"],
        status=_effective_status(proposal),
        display_mode=DisplayMode(proposal.display_mode),
        iva_display=IvaDisplay(proposal.iva_display),
        valid_until=proposal.valid_until,
        total=snapshot["totals"]["total"],
        currency=snapshot["currency"],
        sent_at=proposal.sent_at,
        first_viewed_at=proposal.first_viewed_at,
        last_viewed_at=proposal.last_viewed_at,
        view_count=proposal.view_count,
        content_hash=proposal.content_hash,
    )


# --- Interno (con sesión) ------------------------------------------------------------------


def create_proposal(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int | None, body: ProposalIn
) -> ProposalCreated:
    version_no = body.version_no or freeze_for_proposal(db, ctx, budget_id, if_match)
    version = sendable_version(db, ctx, budget_id, version_no)

    # Al enviar otra, la anterior queda reemplazada (§3.3).
    previous = db.execute(
        select(Proposal)
        .where(
            Proposal.budget_id == version.budget_id, Proposal.status.in_([s.value for s in ACTIVE])
        )
        .with_for_update()
    ).scalars()
    for old in previous:
        old.status = ProposalStatus.SUPERSEDED.value
        _activity(db, old, ActivityType.SUPERSEDED)
    db.flush()

    org = db.get(Organization, ctx.organization_id)
    number = next_number(db, ctx.organization_id, "proposal")
    valid_until = today_ar() + timedelta(days=body.valid_days)
    snapshot = public_snapshot(
        db, version.version_id, display_mode=body.display_mode, iva_display=body.iva_display
    )
    snapshot |= {
        "proposal_number": number,
        "organization": {
            "name": org.name if org else "",
            "legal_name": org.legal_name if org else None,
            "tax_id": org.tax_id if org else None,
        },
        "valid_until": valid_until.isoformat(),
        "terms": (body.terms or "").strip() or None,
        "payment_terms": (body.payment_terms or "").strip() or None,
    }
    PublicSnapshot.model_validate(snapshot)  # lista blanca: falla si se coló una clave
    token = new_token()
    proposal = Proposal(
        organization_id=ctx.organization_id,
        number=number,
        budget_id=version.budget_id,
        budget_version_id=version.version_id,
        token_hash=token_hash(token),
        status=ProposalStatus.SENT.value,
        display_mode=body.display_mode.value,
        iva_display=body.iva_display.value,
        valid_until=valid_until,
        public_snapshot=snapshot,
        content_hash=content_hash(snapshot),
        created_by=ctx.user_id,
    )
    db.add(proposal)
    db.flush()
    _activity(db, proposal, ActivityType.SENT)
    on_proposal_sent(db, ctx, version.event_id)
    _audit(
        db,
        ctx.organization_id,
        ctx.user_id,
        "proposal.sent",
        proposal.id,
        after={"number": number, "version_no": version.version_no, "hash": proposal.content_hash},
    )
    db.flush()
    db.refresh(proposal)
    return ProposalCreated(proposal=_out(proposal), public_path=f"{PUBLIC_PATH}{token}")


def list_proposals(db: AppSession, ctx: TenantContext, budget_id: UUID) -> list[ProposalOut]:
    ensure_budget(db, ctx, budget_id)
    rows = db.execute(
        select(Proposal)
        .where(Proposal.organization_id == ctx.organization_id, Proposal.budget_id == budget_id)
        .order_by(Proposal.sent_at.desc(), Proposal.number.desc())
    ).scalars()
    return [_out(p) for p in rows]


def _proposal(db: AppSession, ctx: TenantContext, proposal_id: UUID) -> Proposal:
    proposal = db.execute(
        select(Proposal)
        .where(Proposal.id == proposal_id, Proposal.organization_id == ctx.organization_id)
        .with_for_update()
    ).scalar_one_or_none()
    if proposal is None:
        raise not_found()
    return proposal


def revoke(db: AppSession, ctx: TenantContext, proposal_id: UUID) -> ProposalOut:
    """Anular: el link deja de mostrar la propuesta."""
    proposal = _proposal(db, ctx, proposal_id)
    if ProposalStatus(proposal.status) not in ACTIVE:
        raise AppError(409, "proposal_not_active", "Solo se anula una propuesta enviada o vista")
    proposal.status = ProposalStatus.REVOKED.value
    proposal.revoked_at = utcnow()
    _activity(db, proposal, ActivityType.REVOKED)
    _audit(db, ctx.organization_id, ctx.user_id, "proposal.revoked", proposal.id)
    db.flush()
    return _out(proposal)


# --- Público (sin sesión, solo el token) -----------------------------------------------------


def _by_token(db: AppSession, raw_token: str) -> Proposal | None:
    """Con solo el hash como capacidad se averigua la organización (política FOR SELECT por
    token) y después se trabaja con el contexto de esa organización."""
    hashed = token_hash(raw_token)
    set_context(db, DbContext(token_hash=hashed))
    org_id = db.execute(
        select(Proposal.organization_id).where(Proposal.token_hash == hashed)
    ).scalar_one_or_none()
    if org_id is None:
        return None
    set_context(db, DbContext(organization_id=org_id, token_hash=hashed))
    return db.execute(
        select(Proposal).where(Proposal.token_hash == hashed).with_for_update()
    ).scalar_one_or_none()


def public_view(db: AppSession, raw_token: str, client: ClientInfo) -> PublicProposal:
    proposal = _by_token(db, raw_token)
    if proposal is None:
        raise AppError(404, "proposal_not_found", "La propuesta no existe")
    if proposal.status == ProposalStatus.REVOKED:
        raise AppError(410, "proposal_revoked", "La productora anuló esta propuesta")
    status = _effective_status(proposal)
    if status is ProposalStatus.EXPIRED and proposal.status != ProposalStatus.EXPIRED:
        proposal.status = ProposalStatus.EXPIRED.value
        _activity(db, proposal, ActivityType.EXPIRED)
    if _is_preview_bot(client.user_agent):
        db.flush()
        return _public_out(proposal, status)
    now = utcnow()
    if proposal.first_viewed_at is None:
        proposal.first_viewed_at = now
        _activity(db, proposal, ActivityType.VIEWED, client)
        _audit(db, proposal.organization_id, None, "proposal.viewed", proposal.id)
    proposal.last_viewed_at = now
    proposal.view_count += 1
    if proposal.status == ProposalStatus.SENT:
        proposal.status = ProposalStatus.VIEWED.value
        status = ProposalStatus.VIEWED
    db.flush()
    return _public_out(proposal, status)


def _public_out(proposal: Proposal, status: ProposalStatus) -> PublicProposal:
    return PublicProposal(
        status=status,
        can_decide=status in ACTIVE,
        content_hash=proposal.content_hash,
        proposal=PublicSnapshot.model_validate(proposal.public_snapshot),
        valid_until=proposal.valid_until,
    )
