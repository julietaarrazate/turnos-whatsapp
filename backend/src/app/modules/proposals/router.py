from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.core.rate_limit import enforce
from app.modules.auth import Client, Public, TenantContext, require
from app.modules.budgets import parse_if_match
from app.modules.proposals import service
from app.modules.proposals.public_schemas import PublicProposal
from app.modules.proposals.schemas import ProposalCreated, ProposalIn, ProposalOut

router = APIRouter(prefix="/api/v1", tags=["proposals"])
public_router = APIRouter(prefix="/api/v1/public", tags=["public"])

View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Send = Annotated[TenantContext, Depends(require(Permission.PROPOSAL_SEND))]
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


@public_router.get("/proposals/{token}", dependencies=[Public])
def public_view(token: Token, db: DbSession, client: Client) -> PublicProposal:
    """Lo que ve el cliente: solo la lista blanca del snapshot (§8.4). Registra la vista."""
    enforce(f"proposal:ip:{client.ip}", limit=120, window_seconds=600)
    return service.public_view(db, token, client)
