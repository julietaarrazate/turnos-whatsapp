from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.core.config import get_settings
from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.notifications import send_email
from app.modules.organizations import service
from app.modules.organizations.schemas import (
    AuditLogOut,
    AuditLogPage,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    MemberOut,
    MemberUpdate,
    OrganizationFiscalUpdate,
    OrganizationOut,
    OrganizationUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["organization"])


OrgView = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
OrgSettings = Annotated[TenantContext, Depends(require(Permission.ORG_SETTINGS_MANAGE))]
OrgFiscal = Annotated[TenantContext, Depends(require(Permission.ORG_FISCAL_MANAGE))]
MembersView = Annotated[TenantContext, Depends(require(Permission.MEMBERS_VIEW))]
MembersManage = Annotated[TenantContext, Depends(require(Permission.MEMBERS_MANAGE))]
AuditView = Annotated[TenantContext, Depends(require(Permission.AUDIT_VIEW))]


@router.get("/organization")
def get_organization(ctx: OrgView, db: DbSession) -> OrganizationOut:
    return service.get_organization(db, ctx)


@router.patch("/organization")
def update_organization(
    body: OrganizationUpdate,
    ctx: OrgSettings,
    db: DbSession,
) -> OrganizationOut:
    return service.update_organization(db, ctx, body)


@router.patch("/organization/fiscal")
def update_fiscal(
    body: OrganizationFiscalUpdate,
    ctx: OrgFiscal,
    db: DbSession,
) -> OrganizationOut:
    return service.update_fiscal(db, ctx, body)


@router.get("/members")
def list_members(ctx: MembersView, db: DbSession) -> list[MemberOut]:
    return service.list_members(db, ctx)


@router.patch("/members/{membership_id}")
def update_member(
    membership_id: UUID,
    body: MemberUpdate,
    ctx: MembersManage,
    db: DbSession,
) -> MemberOut:
    return service.update_member(db, ctx, membership_id, body)


@router.get("/invitations")
def list_invitations(
    ctx: MembersManage,
    db: DbSession,
) -> list[InvitationOut]:
    return [
        InvitationOut(
            id=i.id, email=i.email, role=i.role, created_at=i.created_at, expires_at=i.expires_at
        )
        for i in service.list_invitations(db, ctx)
    ]


@router.post("/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(
    body: InvitationCreate,
    ctx: MembersManage,
    db: DbSession,
    background: BackgroundTasks,
) -> InvitationCreated:
    invitation, message, path = service.invite(db, ctx, body.email, body.role)
    background.add_task(send_email, message)
    return InvitationCreated(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        invite_path=path,
        emailed=get_settings().email_backend != "console",
    )


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invitation_id: UUID,
    ctx: MembersManage,
    db: DbSession,
) -> None:
    service.revoke_invitation(db, ctx, invitation_id)


@router.get("/audit-logs")
def list_audit_logs(
    ctx: AuditView,
    db: DbSession,
    before: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditLogPage:
    rows, cursor = service.list_audit_logs(db, ctx, before, limit)
    return AuditLogPage(
        items=[AuditLogOut.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=cursor,
    )
