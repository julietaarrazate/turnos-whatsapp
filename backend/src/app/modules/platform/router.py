from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.core.db import DbSession
from app.core.errors import AppError
from app.core.rate_limit import enforce
from app.modules.auth import Client, MeResponse, PlatformAdmin, Public, start_session
from app.modules.notifications import send_email
from app.modules.platform import service, signup
from app.modules.platform.schemas import PlatformOverview, SignupIn

router = APIRouter(prefix="/api/v1/admin", tags=["platform"])
signup_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@signup_router.post("/signup", dependencies=[Public])
def create_account(
    body: SignupIn,
    response: Response,
    db: DbSession,
    client: Client,
    background: BackgroundTasks,
) -> MeResponse:
    """Crear cuenta: persona + productora, que queda esperando aprobación."""
    enforce(f"signup:ip:{client.ip}", limit=5, window_seconds=3600)
    if body.website:
        raise AppError(422, "validation_error", "Datos inválidos")
    user, emails = signup.signup(db, body)
    for email in emails:
        background.add_task(send_email, email)
    return start_session(db, response, user, client)


@router.get("/overview")
def get_overview(ctx: PlatformAdmin, db: DbSession) -> PlatformOverview:
    return service.overview(db, ctx)


@router.post("/users/{user_id}/suspend", status_code=status.HTTP_204_NO_CONTENT)
def suspend_user(user_id: UUID, ctx: PlatformAdmin, db: DbSession) -> None:
    service.set_user_active(db, ctx, user_id, active=False)


@router.post("/users/{user_id}/reactivate", status_code=status.HTTP_204_NO_CONTENT)
def reactivate_user(user_id: UUID, ctx: PlatformAdmin, db: DbSession) -> None:
    service.set_user_active(db, ctx, user_id, active=True)


@router.post("/organizations/{organization_id}/suspend", status_code=status.HTTP_204_NO_CONTENT)
def suspend_organization(organization_id: UUID, ctx: PlatformAdmin, db: DbSession) -> None:
    service.set_org_suspended(db, ctx, organization_id, suspended=True)


@router.post("/organizations/{organization_id}/reactivate", status_code=status.HTTP_204_NO_CONTENT)
def reactivate_organization(organization_id: UUID, ctx: PlatformAdmin, db: DbSession) -> None:
    service.set_org_suspended(db, ctx, organization_id, suspended=False)


@router.post("/sessions/{session_id}/close", status_code=status.HTTP_204_NO_CONTENT)
def close_session(session_id: UUID, ctx: PlatformAdmin, db: DbSession) -> None:
    service.revoke_session(db, ctx, session_id)


@router.post("/organizations/{organization_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def approve_organization(
    organization_id: UUID, ctx: PlatformAdmin, db: DbSession, background: BackgroundTasks
) -> None:
    for email in service.approve_organization(db, ctx, organization_id):
        background.add_task(send_email, email)
