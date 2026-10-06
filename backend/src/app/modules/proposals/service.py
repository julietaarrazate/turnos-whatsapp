"""Propuestas: la versión congelada que se publica al cliente (DOMAIN_MODEL §2.7, §3.3)."""

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.core.counters import next_number
from app.core.db import AppSession, DbContext, set_context
from app.core.errors import AppError, not_found
from app.core.security import new_token, token_hash, utcnow
from app.modules.audit import ActorType, record
from app.modules.auth import ClientInfo, TenantContext
from app.modules.budgets import (
    DisplayMode,
    IvaDisplay,
    budget_event_id,
    ensure_budget,
    freeze_for_proposal,
    public_snapshot,
    sendable_version,
)
from app.modules.catalog import today_ar
from app.modules.events import (
    Actor,
    accepts_decisions,
    notification_recipients,
    on_proposal_accepted,
    on_proposal_sent,
)
from app.modules.identity import Organization, User
from app.modules.notifications import Email
from app.modules.proposals.models import (
    ACTIVE,
    DECIDED,
    ActivityType,
    ApprovalMethod,
    Proposal,
    ProposalActivity,
    ProposalStatus,
)
from app.modules.proposals.pdf import render_pdf
from app.modules.proposals.public_schemas import (
    AcceptIn,
    PublicDecision,
    PublicProposal,
    PublicSnapshot,
    RejectIn,
)
from app.modules.proposals.schemas import ApproveIn, ProposalCreated, ProposalIn, ProposalOut

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
    *,
    client: ClientInfo | None = None,
    **changes: Any,
) -> None:
    record(
        db,
        organization_id=organization_id,
        action=action,
        entity_type="proposal",
        entity_id=entity_id,
        actor_user_id=actor,
        actor_type=ActorType.USER if actor else ActorType.PUBLIC_TOKEN,
        ip=client.ip if client else None,
        user_agent=client.user_agent if client else None,
        **changes,
    )


@dataclass(frozen=True)
class _PublicActor:
    """El cliente que decide desde el link: sin usuario, con la organización del token."""

    organization_id: UUID
    client: ClientInfo
    user_id: UUID | None = None


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
        decided_at=proposal.decided_at,
        decided_by_name=proposal.decided_by_name,
        decided_by_email=proposal.decided_by_email,
        decision_comment=proposal.decision_comment,
        approval_method=ApprovalMethod(proposal.approval_method)
        if proposal.approval_method
        else None,
        po_number=proposal.po_number,
    )


# --- Interno (con sesión) ------------------------------------------------------------------


def _sent_emails(
    db: AppSession, ctx: TenantContext, proposal: Proposal, body: ProposalIn, url: str
) -> list[Email]:
    """P-04: el link por email. Responder le llega a quien la envió (reply-to)."""
    sender = db.get(User, ctx.user_id)
    snapshot = proposal.public_snapshot
    org_name = snapshot["organization"]["name"]
    lines = [
        (body.email_message or "").strip()
        or f"Hola! Te compartimos la propuesta para {snapshot['title']}.",
        "",
        f"Verla y responder: {url}",
        f"Válida hasta el {proposal.valid_until.strftime('%d/%m/%Y')}.",
        "",
        sender.name if sender else org_name,
        org_name,
    ]
    return [
        Email(
            to=str(to),
            subject=f"Propuesta de {org_name}: {snapshot['title']}",
            text="\n".join(lines),
            template="proposal_sent",
            reply_to=sender.email if sender else None,
        )
        for to in dict.fromkeys(str(e).lower() for e in body.email_to)
    ]


def create_proposal(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int | None, body: ProposalIn
) -> tuple[ProposalCreated, list[Email]]:
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
        sent_via="EMAIL" if body.email_to else "LINK",
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
        after={
            "number": number,
            "version_no": version.version_no,
            "hash": proposal.content_hash,
            "emailed_to": len(body.email_to),
        },
    )
    db.flush()
    db.refresh(proposal)
    path = f"{PUBLIC_PATH}{token}"
    emails = _sent_emails(db, ctx, proposal, body, f"{get_settings().app_base_url}{path}")
    created = ProposalCreated(
        proposal=_out(proposal), public_path=path, emailed_to=[e.to for e in emails]
    )
    return created, emails


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


def _require_open(proposal: Proposal, *, manual: bool) -> None:
    """Se decide sobre una propuesta enviada o vista. La productora también puede aprobar una
    vencida (la OC llegó tarde); el cliente no."""
    status = _effective_status(proposal)
    if status in ACTIVE or (manual and status is ProposalStatus.EXPIRED):
        return
    if status is ProposalStatus.EXPIRED:
        raise AppError(409, "proposal_expired", "La propuesta venció: pedí una actualización")
    if status is ProposalStatus.SUPERSEDED:
        raise AppError(409, "proposal_superseded", "Hay una propuesta más nueva")
    if status in DECIDED:
        raise AppError(409, "proposal_already_decided", "La propuesta ya tiene una respuesta")
    raise AppError(409, "proposal_not_active", "La propuesta no está vigente")


def _accept(
    db: AppSession,
    actor: Actor,
    proposal: Proposal,
    method: ApprovalMethod,
) -> None:
    """La propuesta pasa a ACCEPTED y su versión, a baseline del evento (§3.3)."""
    event_id = budget_event_id(db, proposal.organization_id, proposal.budget_id)
    proposal.status = ProposalStatus.ACCEPTED.value
    proposal.decided_at = utcnow()
    proposal.approval_method = method.value
    on_proposal_accepted(db, actor, event_id, proposal.budget_version_id)


def _decision_email(
    db: AppSession, actor: Actor, proposal: Proposal, *, accepted: bool, owners: bool
) -> list[Email]:
    event_id = budget_event_id(db, proposal.organization_id, proposal.budget_id)
    event_name, recipients = notification_recipients(db, actor, event_id, include_owners=owners)
    snapshot = proposal.public_snapshot
    verb = "aceptó" if accepted else "rechazó"
    who = proposal.decided_by_name or "El cliente"
    if proposal.approval_method == ApprovalMethod.MANUAL:
        subject = f"Propuesta #{proposal.number} aprobada con OC — {event_name}"
        lead = "Se registró la aprobación manual"
    else:
        subject = f"{who} {verb} la propuesta #{proposal.number} — {event_name}"
        lead = f"{who} {verb} la propuesta online"
    lines = [
        f"{lead} de {snapshot['title']} (v{snapshot['version_no']}).",
        f"Total: {snapshot['currency']} {snapshot['totals']['total']}",
    ]
    if proposal.po_number:
        lines.append(f"OC: {proposal.po_number}")
    if proposal.decision_comment:
        lines.append(f"Comentario: {proposal.decision_comment}")
    link = f"{get_settings().app_base_url}/budgets/{proposal.budget_id}"
    lines.append(f"\nVer el presupuesto: {link}")
    text = "\n".join(lines)
    template = "proposal_accepted" if accepted else "proposal_rejected"
    return [Email(to=to, subject=subject, text=text, template=template) for to in recipients]


def approve(
    db: AppSession, ctx: TenantContext, proposal_id: UUID, body: ApproveIn
) -> tuple[ProposalOut, list[Email]]:
    """Aprobación manual (P-06, MANAGER+): el cliente confirmó por otro canal (OC, email)."""
    proposal = _proposal(db, ctx, proposal_id)
    _require_open(proposal, manual=True)
    proposal.po_number = (body.po_number or "").strip() or None
    proposal.decision_comment = (body.comment or "").strip() or None
    proposal.approved_by_user_id = ctx.user_id
    _accept(db, ctx, proposal, ApprovalMethod.MANUAL)
    _activity(db, proposal, ActivityType.ACCEPTED, ctx.client, method="MANUAL")
    _audit(
        db,
        ctx.organization_id,
        ctx.user_id,
        "proposal.approved",
        proposal.id,
        client=ctx.client,
        after={"po_number": proposal.po_number, "hash": proposal.content_hash},
    )
    db.flush()
    emails = _decision_email(db, ctx, proposal, accepted=True, owners=True)
    return _out(proposal), emails


def _pdf(proposal: Proposal) -> tuple[bytes, str]:
    snapshot = PublicSnapshot.model_validate(proposal.public_snapshot)
    return render_pdf(proposal.content_hash, snapshot), f"propuesta-{proposal.number}.pdf"


def proposal_pdf(db: AppSession, ctx: TenantContext, proposal_id: UUID) -> tuple[bytes, str]:
    """El mismo PDF que baja el cliente, para la productora (no cuenta como descarga)."""
    proposal = db.execute(
        select(Proposal).where(
            Proposal.id == proposal_id, Proposal.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise not_found()
    return _pdf(proposal)


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


def _public_proposal(db: AppSession, raw_token: str) -> Proposal:
    proposal = _by_token(db, raw_token)
    if proposal is None:
        raise AppError(404, "proposal_not_found", "La propuesta no existe")
    if proposal.status == ProposalStatus.REVOKED:
        raise AppError(410, "proposal_revoked", "La productora anuló esta propuesta")
    return proposal


def _first_view_email(db: AppSession, actor: Actor, proposal: Proposal) -> list[Email]:
    event_id = budget_event_id(db, proposal.organization_id, proposal.budget_id)
    event_name, recipients = notification_recipients(db, actor, event_id, include_owners=False)
    link = f"{get_settings().app_base_url}/budgets/{proposal.budget_id}"
    subject = f"El cliente abrió la propuesta #{proposal.number} — {event_name}"
    text = f"{proposal.public_snapshot['title']}: la abrieron por primera vez.\n\n{link}"
    return [
        Email(to=to, subject=subject, text=text, template="proposal_viewed") for to in recipients
    ]


def public_view(
    db: AppSession, raw_token: str, client: ClientInfo
) -> tuple[PublicProposal, list[Email]]:
    proposal = _public_proposal(db, raw_token)
    actor = _PublicActor(organization_id=proposal.organization_id, client=client)
    status = _effective_status(proposal)
    if status is ProposalStatus.EXPIRED and proposal.status != ProposalStatus.EXPIRED:
        proposal.status = ProposalStatus.EXPIRED.value
        _activity(db, proposal, ActivityType.EXPIRED)
    if _is_preview_bot(client.user_agent):
        db.flush()
        return _public_out(db, actor, proposal), []
    now = utcnow()
    emails: list[Email] = []
    if proposal.first_viewed_at is None:
        proposal.first_viewed_at = now
        _activity(db, proposal, ActivityType.VIEWED, client)
        _audit(db, proposal.organization_id, None, "proposal.viewed", proposal.id, client=client)
        emails = _first_view_email(db, actor, proposal)
    proposal.last_viewed_at = now
    proposal.view_count += 1
    if proposal.status == ProposalStatus.SENT:
        proposal.status = ProposalStatus.VIEWED.value
    db.flush()
    return _public_out(db, actor, proposal), emails


def public_pdf(db: AppSession, raw_token: str, client: ClientInfo) -> tuple[bytes, str]:
    """P-03 / P-07: el PDF del link; se registra la descarga (salvo robots de vista previa)."""
    proposal = _public_proposal(db, raw_token)
    if not _is_preview_bot(client.user_agent):
        _activity(db, proposal, ActivityType.PDF_DOWNLOADED, client)
        db.flush()
    return _pdf(proposal)


def _check_hash(proposal: Proposal, seen: str) -> None:
    if seen != proposal.content_hash:
        raise AppError(409, "proposal_changed", "La propuesta cambió: recargá la página")


def public_accept(
    db: AppSession, raw_token: str, body: AcceptIn, client: ClientInfo
) -> tuple[PublicProposal, list[Email]]:
    """P-05: aceptar online. Idempotente: aceptar dos veces devuelve lo mismo."""
    proposal = _public_proposal(db, raw_token)
    actor = _PublicActor(organization_id=proposal.organization_id, client=client)
    if proposal.status == ProposalStatus.ACCEPTED:
        return _public_out(db, actor, proposal), []
    _require_open(proposal, manual=False)
    _check_hash(proposal, body.content_hash)
    event_id = budget_event_id(db, proposal.organization_id, proposal.budget_id)
    if not accepts_decisions(db, actor, event_id, manual=False):
        raise AppError(409, "event_not_open", "Esta propuesta ya no se puede aceptar online")
    _record_decision(proposal, client, body.name, str(body.email), body.comment)
    _accept(db, actor, proposal, ApprovalMethod.ONLINE)
    _activity(db, proposal, ActivityType.ACCEPTED, client, hash=proposal.content_hash)
    _audit(
        db,
        proposal.organization_id,
        None,
        "proposal.accepted",
        proposal.id,
        client=client,
        after={"name": proposal.decided_by_name, "hash": proposal.content_hash},
    )
    db.flush()
    emails = _decision_email(db, actor, proposal, accepted=True, owners=True)
    return _public_out(db, actor, proposal), emails


def public_reject(
    db: AppSession, raw_token: str, body: RejectIn, client: ClientInfo
) -> tuple[PublicProposal, list[Email]]:
    """Rechazar con motivo. No pasa el evento a LOST (§3.1): el cliente puede pedir otra."""
    proposal = _public_proposal(db, raw_token)
    actor = _PublicActor(organization_id=proposal.organization_id, client=client)
    if proposal.status == ProposalStatus.REJECTED:
        return _public_out(db, actor, proposal), []
    _require_open(proposal, manual=False)
    _check_hash(proposal, body.content_hash)
    event_id = budget_event_id(db, proposal.organization_id, proposal.budget_id)
    if not accepts_decisions(db, actor, event_id, manual=False):
        raise AppError(409, "event_not_open", "Esta propuesta ya no se puede responder online")
    email = str(body.email) if body.email else None
    _record_decision(proposal, client, body.name, email, body.reason)
    proposal.status = ProposalStatus.REJECTED.value
    proposal.decided_at = utcnow()
    _activity(db, proposal, ActivityType.REJECTED, client, hash=proposal.content_hash)
    _audit(
        db,
        proposal.organization_id,
        None,
        "proposal.rejected",
        proposal.id,
        client=client,
        after={"reason": proposal.decision_comment, "hash": proposal.content_hash},
    )
    db.flush()
    emails = _decision_email(db, actor, proposal, accepted=False, owners=False)
    return _public_out(db, actor, proposal), emails


def _record_decision(
    proposal: Proposal,
    client: ClientInfo,
    name: str | None,
    email: str | None,
    comment: str | None,
) -> None:
    """Evidencia (I7): quién, desde dónde y sobre qué contenido (el hash ya está guardado)."""
    proposal.decided_by_name = (name or "").strip() or None
    proposal.decided_by_email = email.lower() if email else None
    proposal.decision_comment = (comment or "").strip() or None
    proposal.decision_ip = client.ip
    proposal.decision_user_agent = (client.user_agent or "")[:500] or None


def _public_out(db: AppSession, actor: Actor, proposal: Proposal) -> PublicProposal:
    status = _effective_status(proposal)
    can_decide = status in ACTIVE and accepts_decisions(
        db, actor, budget_event_id(db, proposal.organization_id, proposal.budget_id), manual=False
    )
    decision = (
        PublicDecision(
            status=status,
            decided_at=proposal.decided_at,
            decided_by_name=proposal.decided_by_name,
            method=ApprovalMethod(proposal.approval_method) if proposal.approval_method else None,
        )
        if status in DECIDED and proposal.decided_at is not None
        else None
    )
    return PublicProposal(
        status=status,
        can_decide=can_decide,
        content_hash=proposal.content_hash,
        proposal=PublicSnapshot.model_validate(proposal.public_snapshot),
        valid_until=proposal.valid_until,
        decision=decision,
    )
