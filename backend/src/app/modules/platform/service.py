"""Lecturas y acciones del panel de la plataforma.

La lista de organizaciones se lee con ``platform_admin`` (política de solo lectura sobre
``organizations``). Todo lo de adentro de cada organización se lee entrando a SU contexto de
tenant, una por una: el panel no tiene ninguna otra puerta abierta a los datos de negocio.
"""

from collections import defaultdict
from uuid import UUID

import structlog
from sqlalchemy import func, select, update

from app.core.db import AppSession, DbContext, set_context
from app.core.errors import AppError
from app.core.security import utcnow
from app.modules.audit import AuditLog
from app.modules.auth import AuthSession, PlatformContext
from app.modules.budgets import Budget
from app.modules.events import Event
from app.modules.identity import Membership, Organization, User
from app.modules.platform.schemas import (
    OrgMemberOut,
    PlatformActivityOut,
    PlatformOrgOut,
    PlatformOverview,
    PlatformSessionOut,
    PlatformUserOut,
    UserOrgOut,
)

log = structlog.get_logger()

ACTIVITY_PER_ORG = 50
ACTIVITY_TOTAL = 150


def _hidden() -> AppError:
    return AppError(404, "not_found", "No encontrado")


def _organizations(db: AppSession, ctx: PlatformContext) -> list[Organization]:
    set_context(db, DbContext(user_id=ctx.user_id, platform_admin=True))
    orgs = list(db.scalars(select(Organization).order_by(Organization.created_at)))
    set_context(db, DbContext(user_id=ctx.user_id))
    return orgs


def overview(db: AppSession, ctx: PlatformContext) -> PlatformOverview:
    now = utcnow()
    users = {u.id: u for u in db.scalars(select(User).order_by(User.created_at))}
    orgs = _organizations(db, ctx)
    org_names = {o.id: o.name for o in orgs}

    org_out: list[PlatformOrgOut] = []
    user_orgs: dict[UUID, list[UserOrgOut]] = defaultdict(list)
    activity: list[PlatformActivityOut] = []
    for org in orgs:
        set_context(db, DbContext(organization_id=org.id))
        members = list(db.scalars(select(Membership).order_by(Membership.created_at)))
        events = db.scalar(
            select(func.count()).select_from(Event).where(Event.deleted_at.is_(None))
        )
        budgets = db.scalar(select(func.count()).select_from(Budget))
        last = db.scalar(select(func.max(AuditLog.created_at)))
        for row in db.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(ACTIVITY_PER_ORG)
        ):
            actor = users.get(row.actor_user_id) if row.actor_user_id else None
            activity.append(
                PlatformActivityOut(
                    created_at=row.created_at,
                    organization_name=org.name,
                    user_name=actor.name if actor else None,
                    actor_type=row.actor_type,
                    action=row.action,
                    entity_type=row.entity_type,
                )
            )
        member_out = []
        for m in members:
            u = users.get(m.user_id)
            if u is None:
                continue
            member_out.append(
                OrgMemberOut(user_id=u.id, name=u.name, email=u.email, role=m.role, status=m.status)
            )
            user_orgs[u.id].append(
                UserOrgOut(
                    organization_id=org.id,
                    organization_name=org.name,
                    role=m.role,
                    status=m.status,
                )
            )
        org_out.append(
            PlatformOrgOut(
                id=org.id,
                name=org.name,
                created_at=org.created_at,
                suspended_at=org.suspended_at,
                members=member_out,
                events=events or 0,
                budgets=budgets or 0,
                last_activity_at=last,
            )
        )
    set_context(db, DbContext(user_id=ctx.user_id))

    open_sessions = list(
        db.scalars(
            select(AuthSession)
            .where(AuthSession.revoked_at.is_(None), AuthSession.expires_at > now)
            .order_by(AuthSession.last_used_at.desc())
        )
    )
    seen_rows = db.execute(
        select(AuthSession.user_id, func.max(AuthSession.last_used_at)).group_by(
            AuthSession.user_id
        )
    )
    last_seen = {row[0]: row[1] for row in seen_rows}
    sessions_by_user: dict[UUID, int] = defaultdict(int)
    for s in open_sessions:
        sessions_by_user[s.user_id] += 1

    activity.sort(key=lambda a: a.created_at, reverse=True)
    return PlatformOverview(
        organizations=org_out,
        users=[
            PlatformUserOut(
                id=u.id,
                name=u.name,
                email=u.email,
                is_active=u.is_active,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
                last_seen_at=last_seen.get(u.id),
                open_sessions=sessions_by_user[u.id],
                organizations=user_orgs[u.id],
                is_me=u.id == ctx.user_id,
            )
            for u in users.values()
        ],
        sessions=[
            PlatformSessionOut(
                id=s.id,
                user_id=s.user_id,
                user_name=users[s.user_id].name if s.user_id in users else "",
                organization_name=org_names.get(s.active_organization_id)
                if s.active_organization_id
                else None,
                created_at=s.created_at,
                last_used_at=s.last_used_at,
                ip=s.ip,
                user_agent=s.user_agent,
                is_current=s.id == ctx.session_id,
            )
            for s in open_sessions
        ],
        activity=activity[:ACTIVITY_TOTAL],
    )


def _revoke_user_sessions(db: AppSession, user_id: UUID, reason: str) -> int:
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )
    return int(getattr(result, "rowcount", 0) or 0)


def set_user_active(db: AppSession, ctx: PlatformContext, user_id: UUID, active: bool) -> None:
    if user_id == ctx.user_id:
        raise AppError(409, "cannot_suspend_self", "No podés suspenderte a vos misma")
    user = db.get(User, user_id)
    if user is None:
        raise _hidden()
    user.is_active = active
    closed = 0 if active else _revoke_user_sessions(db, user_id, "platform_suspended")
    log.info(
        "platform.user_active_changed",
        admin_id=str(ctx.user_id),
        user_id=str(user_id),
        active=active,
        sessions_closed=closed,
    )


def set_org_suspended(
    db: AppSession, ctx: PlatformContext, organization_id: UUID, suspended: bool
) -> None:
    set_context(db, DbContext(organization_id=organization_id))
    org = db.get(Organization, organization_id)
    if org is None:
        raise _hidden()
    org.suspended_at = utcnow() if suspended else None
    db.flush()
    set_context(db, DbContext(user_id=ctx.user_id))
    log.info(
        "platform.organization_suspended_changed",
        admin_id=str(ctx.user_id),
        organization_id=str(organization_id),
        suspended=suspended,
    )


def revoke_session(db: AppSession, ctx: PlatformContext, session_id: UUID) -> None:
    if session_id == ctx.session_id:
        raise AppError(409, "cannot_close_own_session", "Esta es tu sesión actual")
    session = db.get(AuthSession, session_id)
    if session is None or session.revoked_at is not None:
        raise _hidden()
    session.revoked_at = utcnow()
    session.revoked_reason = "platform_closed"
    log.info(
        "platform.session_closed",
        admin_id=str(ctx.user_id),
        session_id=str(session_id),
        user_id=str(session.user_id),
    )
