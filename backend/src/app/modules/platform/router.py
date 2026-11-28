from uuid import UUID

from fastapi import APIRouter, status

from app.core.db import DbSession
from app.modules.auth import PlatformAdmin
from app.modules.platform import service
from app.modules.platform.schemas import PlatformOverview

router = APIRouter(prefix="/api/v1/admin", tags=["platform"])


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
