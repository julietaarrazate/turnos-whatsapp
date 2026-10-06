from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Path, Response, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.core.rate_limit import enforce
from app.modules.auth import Client, Public, TenantContext, require
from app.modules.budgets import parse_if_match
from app.modules.notifications import Email, send_email
from app.modules.proposals import service
from app.modules.proposals.public_schemas import AcceptIn, PublicProposal, RejectIn
from app.modules.proposals.schemas import ApproveIn, ProposalCreated, ProposalIn, ProposalOut

router = APIRouter(prefix="/api/v1", tags=["proposals"])
public_router = APIRouter(prefix="/api/v1/public", tags=["public"])

View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Send = Annotated[TenantContext, Depends(require(Permission.PROPOSAL_SEND))]
Decide = Annotated[TenantContext, Depends(require(Permission.PROPOSAL_DECIDE))]
OptionalIfMatch = Annotated[str | None, Header(alias="If-Match", max_length=40)]
Token = Annotated[str, Path(min_length=20, max_length=100)]


@router.post("/budgets/{budget_id}/proposals", status_code=status.HTTP_201_CREATED)
def create_proposal(
    budget_id: UUID, body: ProposalIn, ctx: Send, db: DbSession, if_match: OptionalIfMatch = None
) -> ProposalCreated:
    """Generar propuesta: congela el borrador (If-Match) o usa la versión indicada, reemplaza la
    propuesta activa anterior y devuelve el link público (una sola vez)."""
    lock = parse_if_match(if_match) if if_match is not None else None
    return service.create_proposal(db, ctx, budget_id, lock, body)


@router.get("/budgets/{budget_id}/proposals")
def list_proposals(budget_id: UUID, ctx: View, db: DbSession) -> list[ProposalOut]:
    return service.list_proposals(db, ctx, budget_id)


@router.post("/proposals/{proposal_id}/revoke")
def revoke(proposal_id: UUID, ctx: Send, db: DbSession) -> ProposalOut:
    return service.revoke(db, ctx, proposal_id)


_PDF: dict[int | str, dict[str, Any]] = {
    200: {"content": {"application/pdf": {}}, "description": "PDF de la propuesta"}
}


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Si la anulan, el link deja de servir: nada de caches intermedios.
            "Cache-Control": "private, no-store",
        },
    )


def _notify(background: BackgroundTasks, emails: list[Email]) -> None:
    """Los avisos salen después del commit: si la transacción falla, no se manda nada."""
    for email in emails:
        background.add_task(send_email, email)


@router.post("/proposals/{proposal_id}/approve")
def approve(
    proposal_id: UUID, body: ApproveIn, ctx: Decide, db: DbSession, background: BackgroundTasks
) -> ProposalOut:
    """Aprobación manual con OC (MANAGER+): la versión pasa a ser la baseline del evento."""
    result, emails = service.approve(db, ctx, proposal_id, body)
    _notify(background, emails)
    return result


@router.get("/proposals/{proposal_id}/pdf", response_class=Response, responses=_PDF)
def proposal_pdf(proposal_id: UUID, ctx: View, db: DbSession) -> Response:
    return _pdf_response(*service.proposal_pdf(db, ctx, proposal_id))


@public_router.get(
    "/proposals/{token}/pdf", dependencies=[Public], response_class=Response, responses=_PDF
)
def public_pdf(token: Token, db: DbSession, client: Client) -> Response:
    """El PDF que descarga el cliente: mismo contenido que el link (P-03)."""
    enforce(f"proposal-pdf:ip:{client.ip}", limit=30, window_seconds=600)
    return _pdf_response(*service.public_pdf(db, token, client))


@public_router.get("/proposals/{token}", dependencies=[Public])
def public_view(
    token: Token, db: DbSession, client: Client, background: BackgroundTasks
) -> PublicProposal:
    """Lo que ve el cliente: solo la lista blanca del snapshot (§8.4). Registra la vista."""
    enforce(f"proposal:ip:{client.ip}", limit=120, window_seconds=600)
    result, emails = service.public_view(db, token, client)
    _notify(background, emails)
    return result


@public_router.post("/proposals/{token}/accept", dependencies=[Public])
def public_accept(
    token: Token, body: AcceptIn, db: DbSession, client: Client, background: BackgroundTasks
) -> PublicProposal:
    """Aceptar online con nombre y email; queda la evidencia (IP, navegador, hash)."""
    enforce(f"proposal-decision:ip:{client.ip}", limit=20, window_seconds=600)
    result, emails = service.public_accept(db, token, body, client)
    _notify(background, emails)
    return result


@public_router.post("/proposals/{token}/reject", dependencies=[Public])
def public_reject(
    token: Token, body: RejectIn, db: DbSession, client: Client, background: BackgroundTasks
) -> PublicProposal:
    """Rechazar con motivo."""
    enforce(f"proposal-decision:ip:{client.ip}", limit=20, window_seconds=600)
    result, emails = service.public_reject(db, token, body, client)
    _notify(background, emails)
    return result
