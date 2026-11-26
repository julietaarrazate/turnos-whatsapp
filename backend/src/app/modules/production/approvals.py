"""Aprobación de diseños por link: el cliente abre el link en el teléfono, sin cuenta, ve el
render o el arte y responde "Aprobado" o "Pido cambios". Queda quién, cuándo y qué dijo.

Mismo esquema que el link público de propuestas (ARCHITECTURE §8.4): el token viaja solo en el
link, en la base queda el hash; con el hash se averigua la organización y el resto corre con su
contexto. Lo que ve el cliente es una lista blanca: el título y el archivo, nada más del evento.
"""

from datetime import timedelta
from uuid import UUID

from fastapi import Response
from sqlalchemy import func, select, update

from app.core.db import AppSession, DbContext, set_context
from app.core.errors import AppError, not_found
from app.core.security import new_token, token_hash, utcnow
from app.modules.audit import ActorType, record
from app.modules.auth import ClientInfo, TenantContext
from app.modules.documents import Document, DocumentKind, file_response, get_document
from app.modules.events import Event
from app.modules.identity import Organization
from app.modules.production.files import _can_edit
from app.modules.production.models import ApprovalStatus, EventFile, FileApproval
from app.modules.production.schemas import (
    ApprovalDecisionIn,
    ApprovalLinkOut,
    ApprovalOut,
    PublicApproval,
)
from app.modules.production.service import _audit, _editable_event

LINK_TTL = timedelta(days=30)


def _out(approval: FileApproval, rounds: int) -> ApprovalOut:
    return ApprovalOut(
        id=approval.id,
        status=approval.status,
        requested_at=approval.created_at,
        decided_at=approval.decided_at,
        decided_by_name=approval.decided_by_name,
        comment=approval.comment,
        rounds=rounds,
    )


def latest_by_file(
    db: AppSession, organization_id: UUID, file_ids: list[UUID]
) -> dict[UUID, ApprovalOut]:
    """El último pedido (sin contar los reemplazados) y cuántas vueltas lleva cada archivo."""
    if not file_ids:
        return {}
    rows = db.execute(
        select(FileApproval)
        .where(
            FileApproval.organization_id == organization_id,
            FileApproval.file_id.in_(file_ids),
            FileApproval.status != ApprovalStatus.REPLACED.value,
        )
        .order_by(FileApproval.file_id, FileApproval.created_at)
    ).scalars()
    result: dict[UUID, ApprovalOut] = {}
    counts: dict[UUID, int] = {}
    for approval in rows:
        counts[approval.file_id] = counts.get(approval.file_id, 0) + 1
        result[approval.file_id] = _out(approval, counts[approval.file_id])
    return result


def request(db: AppSession, ctx: TenantContext, file_id: UUID) -> ApprovalLinkOut:
    """Arma un link nuevo. Si había uno sin responder, ese deja de servir (queda uno vivo)."""
    if not _can_edit(ctx):
        raise AppError(
            403, "files_read_only", "Tu rol puede ver los archivos, no pedir aprobaciones"
        )
    file = db.execute(
        select(EventFile).where(
            EventFile.id == file_id, EventFile.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if file is None:
        raise not_found()
    _editable_event(db, ctx, file.event_id)
    now = utcnow()
    db.execute(
        update(FileApproval)
        .where(
            FileApproval.organization_id == ctx.organization_id,
            FileApproval.file_id == file.id,
            FileApproval.status == ApprovalStatus.PENDING.value,
        )
        .values(status=ApprovalStatus.REPLACED.value)
    )
    token = new_token()
    approval = FileApproval(
        organization_id=ctx.organization_id,
        event_id=file.event_id,
        file_id=file.id,
        token_hash=token_hash(token),
        status=ApprovalStatus.PENDING.value,
        requested_by=ctx.user_id,
        expires_at=now + LINK_TTL,
    )
    db.add(approval)
    db.flush()
    db.refresh(approval)
    rounds = db.execute(
        select(func.count()).where(
            FileApproval.organization_id == ctx.organization_id,
            FileApproval.file_id == file.id,
            FileApproval.status != ApprovalStatus.REPLACED.value,
        )
    ).scalar_one()
    _audit(db, ctx, "file.approval_requested", file.event_id, after={"title": file.title})
    return ApprovalLinkOut(approval=_out(approval, rounds), path=f"/a/{token}")


# --- Lo que hace el cliente con el link (sin sesión) ------------------------------------


def _by_token(db: AppSession, raw_token: str, *, lock: bool = False) -> FileApproval:
    hashed = token_hash(raw_token)
    set_context(db, DbContext(token_hash=hashed))
    org_id = db.execute(
        select(FileApproval.organization_id).where(FileApproval.token_hash == hashed)
    ).scalar_one_or_none()
    if org_id is None:
        raise not_found("approval_not_found", "El link no existe o ya no sirve")
    set_context(db, DbContext(organization_id=org_id, token_hash=hashed))
    query = select(FileApproval).where(FileApproval.token_hash == hashed)
    approval = db.execute(query.with_for_update() if lock else query).scalar_one_or_none()
    if approval is None:
        raise not_found("approval_not_found", "El link no existe o ya no sirve")
    return approval


def _status(approval: FileApproval) -> str:
    if approval.status == ApprovalStatus.PENDING.value and approval.expires_at <= utcnow():
        return "EXPIRED"
    return approval.status


def _file(db: AppSession, approval: FileApproval) -> tuple[EventFile, Document | None]:
    file = db.execute(
        select(EventFile).where(
            EventFile.id == approval.file_id,
            EventFile.organization_id == approval.organization_id,
        )
    ).scalar_one()
    document = (
        get_document(db, approval.organization_id, file.document_id, DocumentKind.EVENT_FILE)
        if file.document_id
        else None
    )
    return file, document


def _public(db: AppSession, approval: FileApproval) -> PublicApproval:
    file, document = _file(db, approval)
    event = db.execute(select(Event).where(Event.id == approval.event_id)).scalar_one()
    org = db.execute(
        select(Organization).where(Organization.id == approval.organization_id)
    ).scalar_one()
    if document is None:
        kind = "LINK"
    elif document.mime.startswith("image/"):
        kind = "IMAGE"
    else:
        kind = "PDF"
    return PublicApproval(
        organization_name=org.name,
        event_name=event.name,
        title=file.title,
        kind=kind,
        url=file.url,
        status=_status(approval),
        decided_at=approval.decided_at,
        decided_by_name=approval.decided_by_name,
        comment=approval.comment,
    )


def public_view(db: AppSession, raw_token: str) -> PublicApproval:
    return _public(db, _by_token(db, raw_token))


def public_file(db: AppSession, raw_token: str) -> Response:
    approval = _by_token(db, raw_token)
    if _status(approval) in {"REPLACED", "EXPIRED"}:
        raise not_found("approval_not_found", "El link no existe o ya no sirve")
    _, document = _file(db, approval)
    if document is None:
        raise not_found()
    return file_response(document)


def decide(
    db: AppSession, raw_token: str, body: ApprovalDecisionIn, client: ClientInfo
) -> PublicApproval:
    approval = _by_token(db, raw_token, lock=True)
    status = _status(approval)
    if status == "EXPIRED":
        raise AppError(410, "approval_expired", "El link venció: pedile uno nuevo a la productora")
    if status == "REPLACED":
        raise AppError(410, "approval_replaced", "Hay una versión más nueva: pedí el link nuevo")
    if status != ApprovalStatus.PENDING.value:
        raise AppError(409, "approval_decided", "Este diseño ya tiene respuesta")
    comment = (body.comment or "").strip() or None
    if body.decision == "CHANGES" and not comment:
        raise AppError(422, "comment_required", "Contanos qué cambios necesitás")
    approval.status = body.decision
    approval.decided_at = utcnow()
    approval.decided_by_name = body.name.strip()
    approval.comment = comment
    approval.decision_ip = client.ip
    approval.decision_user_agent = (client.user_agent or "")[:400] or None
    file, _ = _file(db, approval)
    record(
        db,
        organization_id=approval.organization_id,
        action="file.approval_decided",
        entity_type="event",
        entity_id=approval.event_id,
        actor_user_id=None,
        actor_type=ActorType.PUBLIC_TOKEN,
        after={
            "title": file.title,
            "status": approval.status,
            "by": approval.decided_by_name,
            "note": comment,
            "approval_id": str(approval.id),
        },
        ip=client.ip,
        user_agent=client.user_agent,
    )
    return _public(db, approval)
