"""Administración de la organización: datos, miembros, invitaciones y auditoría."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update

from app.core.db import AppSession
from app.core.enums import Role
from app.core.errors import AppError, ensure, not_found
from app.core.permissions import VIEWER_SEES_FINANCIALS, Permission
from app.core.security import utcnow
from app.modules.audit import AuditLog, diff, record
from app.modules.auth import Invitation, TenantContext, create_invitation
from app.modules.identity import FOLLOW_UP_DAYS, Membership, MembershipStatus, Organization, User
from app.modules.notifications import Email
from app.modules.organizations.schemas import (
    MemberOut,
    MemberUpdate,
    OrganizationFiscalUpdate,
    OrganizationOut,
    OrganizationUpdate,
)


def _audit(
    db: AppSession,
    ctx: TenantContext,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    record(
        db,
        organization_id=ctx.organization_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=ctx.user_id,
        before=before,
        after=after,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
    )


# --- Organización ------------------------------------------------------------------------


def _org(db: AppSession, ctx: TenantContext) -> Organization:
    return ensure(db.get(Organization, ctx.organization_id), "organización")


def organization_out(org: Organization) -> OrganizationOut:
    return OrganizationOut(
        id=org.id,
        name=org.name,
        legal_name=org.legal_name,
        tax_id=org.tax_id,
        tax_condition=org.tax_condition,
        base_currency=org.base_currency,
        timezone=org.timezone,
        viewer_sees_financials=bool(org.settings.get(VIEWER_SEES_FINANCIALS, False)),
        follow_up_days=org.follow_up_days,
    )


def get_organization(db: AppSession, ctx: TenantContext) -> OrganizationOut:
    return organization_out(_org(db, ctx))


def update_organization(
    db: AppSession, ctx: TenantContext, body: OrganizationUpdate
) -> OrganizationOut:
    org = _org(db, ctx)
    before = organization_out(org).model_dump(mode="json")
    if body.name is not None:
        org.name = body.name.strip()
    if body.viewer_sees_financials is not None:
        org.settings = {**org.settings, VIEWER_SEES_FINANCIALS: body.viewer_sees_financials}
    if body.follow_up_days is not None:
        org.settings = {**org.settings, FOLLOW_UP_DAYS: body.follow_up_days}
    db.flush()
    after = organization_out(org).model_dump(mode="json")
    old, new = diff(before, after)
    if new:
        _audit(
            db,
            ctx,
            action="org.settings_changed",
            entity_type="organization",
            entity_id=org.id,
            before=old,
            after=new,
        )
    return organization_out(org)


def update_fiscal(
    db: AppSession, ctx: TenantContext, body: OrganizationFiscalUpdate
) -> OrganizationOut:
    org = _org(db, ctx)
    before = organization_out(org).model_dump(mode="json")
    for field in body.model_fields_set:
        value = getattr(body, field)
        setattr(org, field, value.value if field == "tax_condition" and value else value)
    db.flush()
    old, new = diff(before, organization_out(org).model_dump(mode="json"))
    if new:
        _audit(
            db,
            ctx,
            action="org.fiscal_changed",
            entity_type="organization",
            entity_id=org.id,
            before=old,
            after=new,
        )
    return organization_out(org)


# --- Miembros ----------------------------------------------------------------------------


def list_members(db: AppSession, ctx: TenantContext) -> list[MemberOut]:
    show_email = ctx.can(Permission.MEMBERS_MANAGE)
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.organization_id)
        .order_by(User.name)
    ).all()
    return [
        MemberOut(
            membership_id=m.id,
            user_id=u.id,
            name=u.name,
            email=u.email if show_email else None,
            role=m.role,
            status=m.status,
        )
        for m, u in rows
    ]


def _active_owner_count(db: AppSession, organization_id: UUID) -> int:
    return db.execute(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.role == Role.OWNER,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ).scalar_one()


def update_member(
    db: AppSession, ctx: TenantContext, membership_id: UUID, body: MemberUpdate
) -> MemberOut:
    membership = db.execute(
        select(Membership)
        .where(Membership.id == membership_id, Membership.organization_id == ctx.organization_id)
        .with_for_update()
    ).scalar_one_or_none()
    if membership is None:
        raise not_found()
    touches_owner = Role.OWNER in {membership.role, body.role}
    if touches_owner and ctx.role is not Role.OWNER:
        raise AppError(403, "owner_required", "Solo un OWNER puede asignar o modificar a un OWNER")
    if membership.id == ctx.membership_id and body.status == MembershipStatus.DISABLED:
        raise AppError(409, "cannot_disable_self", "No podés desactivarte a vos misma/o")

    before = {"role": membership.role, "status": membership.status}
    if body.role is not None:
        membership.role = body.role.value
    if body.status is not None:
        if body.status == MembershipStatus.INVITED:
            raise AppError(422, "invalid_status", "Estado inválido")
        membership.status = body.status.value
    db.flush()
    if _active_owner_count(db, ctx.organization_id) == 0:
        raise AppError(409, "last_owner", "La organización necesita al menos un OWNER activo")

    old, new = diff(before, {"role": membership.role, "status": membership.status})
    if new:
        action = "membership.disabled" if new.get("status") == "DISABLED" else "membership.changed"
        _audit(
            db,
            ctx,
            action=action,
            entity_type="membership",
            entity_id=membership.id,
            before=old,
            after=new,
        )
    user = ensure(db.get(User, membership.user_id), "usuario")
    return MemberOut(
        membership_id=membership.id,
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=membership.role,
        status=membership.status,
    )


# --- Invitaciones --------------------------------------------------------------------------


def list_invitations(db: AppSession, ctx: TenantContext) -> list[Invitation]:
    return list(
        db.execute(
            select(Invitation)
            .where(
                Invitation.organization_id == ctx.organization_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > utcnow(),
            )
            .order_by(Invitation.created_at.desc())
        ).scalars()
    )


def invite(db: AppSession, ctx: TenantContext, email: str, role: Role) -> tuple[Invitation, Email]:
    if role is Role.OWNER and ctx.role is not Role.OWNER:
        raise AppError(403, "owner_required", "Solo un OWNER puede invitar a otro OWNER")
    already = db.execute(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == ctx.organization_id,
            Membership.status == MembershipStatus.ACTIVE,
            func.lower(User.email) == email.strip().lower(),
        )
    ).first()
    if already is not None:
        raise AppError(409, "already_member", "Esa persona ya es parte de la organización")
    invitation, message = create_invitation(
        db, ctx.organization_id, email, role, invited_by_membership_id=ctx.membership_id
    )
    _audit(
        db,
        ctx,
        action="membership.invited",
        entity_type="invitation",
        entity_id=invitation.id,
        after={"email": invitation.email, "role": invitation.role},
    )
    return invitation, message


def revoke_invitation(db: AppSession, ctx: TenantContext, invitation_id: UUID) -> None:
    result = db.execute(
        update(Invitation)
        .where(
            Invitation.id == invitation_id,
            Invitation.organization_id == ctx.organization_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise not_found()
    _audit(db, ctx, action="invitation.revoked", entity_type="invitation", entity_id=invitation_id)


# --- Auditoría ---------------------------------------------------------------------------


def list_audit_logs(
    db: AppSession, ctx: TenantContext, before: UUID | None, limit: int
) -> tuple[list[AuditLog], UUID | None]:
    query = select(AuditLog).where(AuditLog.organization_id == ctx.organization_id)
    if before is not None:
        query = query.where(AuditLog.id < before)  # UUIDv7: ordenado por tiempo
    rows = list(db.execute(query.order_by(AuditLog.id.desc()).limit(limit + 1)).scalars())
    next_cursor = rows[limit - 1].id if len(rows) > limit else None
    return rows[:limit], next_cursor
