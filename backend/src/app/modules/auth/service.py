"""Casos de uso de autenticación. No conoce HTTP: el router traduce a cookies y respuestas."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.db import AppSession, DbContext, session_scope, set_context
from app.core.enums import Role
from app.core.errors import AppError, ensure
from app.core.permissions import Permission, permissions_for
from app.core.security import (
    AccessClaims,
    decode_access_token,
    encode_access_token,
    hash_password,
    new_token,
    password_needs_rehash,
    token_hash,
    utcnow,
    verify_password,
)
from app.modules.audit import ActorType, record
from app.modules.auth.models import AuthSession, Invitation, PasswordResetToken, RefreshToken
from app.modules.identity import Membership, MembershipStatus, Organization, User
from app.modules.notifications import Email


@dataclass(frozen=True)
class ClientInfo:
    ip: str | None
    user_agent: str | None


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    session_id: UUID


@dataclass(frozen=True)
class AuthContext:
    """Quién hace el request. ``organization_id`` es None si el usuario no tiene org activa."""

    user_id: UUID
    session_id: UUID
    organization_id: UUID | None
    membership_id: UUID | None
    role: Role | None
    permissions: frozenset[Permission]


@dataclass(frozen=True)
class TenantContext:
    """Usuario con organización activa y permisos ya verificados para el endpoint."""

    user_id: UUID
    session_id: UUID
    organization_id: UUID
    membership_id: UUID
    role: Role
    permissions: frozenset[Permission]
    client: ClientInfo

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


def _unauthorized(code: str = "unauthenticated", detail: str = "Sesión inválida") -> AppError:
    return AppError(401, code, detail)


def find_user_by_email(db: AppSession, email: str) -> User | None:
    return db.execute(
        select(User).where(func.lower(User.email) == email.strip().lower())
    ).scalar_one_or_none()


def active_memberships(db: AppSession, user_id: UUID) -> list[tuple[Membership, Organization]]:
    """Membresías activas del usuario en todas sus organizaciones (requiere contexto de usuario)."""
    set_context(db, DbContext(user_id=user_id))
    rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(Membership.created_at)
    ).all()
    return [(m, o) for m, o in rows]


def _issue_tokens(
    db: AppSession,
    user: User,
    organization_id: UUID | None,
    client: ClientInfo,
    session: AuthSession | None = None,
) -> IssuedTokens:
    settings = get_settings()
    now = utcnow()
    expires = now + timedelta(days=settings.refresh_token_ttl_days)
    if session is None:
        session = AuthSession(
            user_id=user.id,
            active_organization_id=organization_id,
            expires_at=expires,
            ip=client.ip,
            user_agent=(client.user_agent or "")[:400] or None,
        )
        db.add(session)
        db.flush()
    else:
        session.active_organization_id = organization_id
        session.last_used_at = now
        session.expires_at = expires
    raw_refresh = new_token()
    db.add(
        RefreshToken(session_id=session.id, token_hash=token_hash(raw_refresh), expires_at=expires)
    )
    access = encode_access_token(
        AccessClaims(user_id=user.id, session_id=session.id, organization_id=organization_id)
    )
    return IssuedTokens(access_token=access, refresh_token=raw_refresh, session_id=session.id)


def login(db: AppSession, email: str, password: str, client: ClientInfo) -> IssuedTokens:
    user = find_user_by_email(db, email)
    valid = verify_password(user.password_hash if user else None, password)
    if user is None or not valid or not user.is_active:
        raise _unauthorized("invalid_credentials", "Email o contraseña incorrectos")
    if password_needs_rehash(ensure(user.password_hash, "password_hash")):
        user.password_hash = hash_password(password)
    return login_user(db, user, client)


def login_user(db: AppSession, user: User, client: ClientInfo) -> IssuedTokens:
    """Abre una sesión para alguien ya verificado (contraseña o llave de acceso)."""
    user.last_login_at = utcnow()
    memberships = active_memberships(db, user.id)
    organization_id = memberships[0][0].organization_id if memberships else None
    return _issue_tokens(db, user, organization_id, client)


def _revoke_session_now(session_id: UUID, reason: str) -> None:
    """Revoca en una transacción propia: debe persistir aunque el request termine en error."""
    with session_scope() as db:
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow(), revoked_reason=reason)
        )


def refresh(db: AppSession, raw_token: str | None, client: ClientInfo) -> IssuedTokens:
    if not raw_token:
        raise _unauthorized()
    row = db.execute(
        select(RefreshToken, AuthSession)
        .join(AuthSession, AuthSession.id == RefreshToken.session_id)
        .where(RefreshToken.token_hash == token_hash(raw_token))
        .with_for_update(of=RefreshToken)
    ).first()
    if row is None:
        raise _unauthorized()
    token, session = row
    now = utcnow()
    if session.revoked_at is not None or session.expires_at <= now or token.expires_at <= now:
        raise _unauthorized("session_expired", "La sesión expiró")
    if token.used_at is not None:
        grace = timedelta(seconds=get_settings().refresh_reuse_grace_seconds)
        if now - token.used_at > grace:
            # Un token ya rotado volvió a usarse: posible robo. Se corta toda la familia.
            _revoke_session_now(session.id, "refresh_token_reuse")
            raise _unauthorized("session_revoked", "La sesión fue revocada")
    else:
        token.used_at = now

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    organization_id = session.active_organization_id
    if organization_id is not None:
        valid_orgs = {m.organization_id for m, _ in active_memberships(db, user.id)}
        if organization_id not in valid_orgs:
            organization_id = next(iter(valid_orgs), None)
    return _issue_tokens(db, user, organization_id, client, session=session)


def logout(db: AppSession, raw_refresh: str | None, session_id: UUID | None) -> None:
    if raw_refresh:
        token = db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw_refresh))
        ).scalar_one_or_none()
        session_id = token.session_id if token else session_id
    if session_id is not None:
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow(), revoked_reason="logout")
        )


def resolve_access_token(db: AppSession, raw: str | None) -> AuthContext:
    claims = decode_access_token(raw) if raw else None
    if claims is None:
        raise _unauthorized()
    session = db.get(AuthSession, claims.session_id)
    now = utcnow()
    if (
        session is None
        or session.user_id != claims.user_id
        or session.revoked_at is not None
        or session.expires_at <= now
    ):
        raise _unauthorized()
    user = db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()

    if claims.organization_id is None:
        set_context(db, DbContext(user_id=user.id))
        return AuthContext(user.id, session.id, None, None, None, frozenset())

    set_context(db, DbContext(organization_id=claims.organization_id, user_id=user.id))
    row = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.organization_id == claims.organization_id,
            Membership.user_id == user.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ).first()
    if row is None:
        # La membresía se revocó: el acceso se corta en el próximo request, sin esperar al JWT.
        raise AppError(403, "membership_inactive", "Ya no tenés acceso a esta organización")
    membership, org = row
    role = Role(membership.role)
    return AuthContext(
        user_id=user.id,
        session_id=session.id,
        organization_id=org.id,
        membership_id=membership.id,
        role=role,
        permissions=permissions_for(role, org.settings),
    )


def switch_organization(
    db: AppSession, auth: AuthContext, organization_id: UUID, client: ClientInfo
) -> IssuedTokens:
    valid = {m.organization_id for m, _ in active_memberships(db, auth.user_id)}
    if organization_id not in valid:
        raise AppError(404, "not_found", "Organización no encontrada")
    session = ensure(db.get(AuthSession, auth.session_id), "sesión")
    user = ensure(db.get(User, auth.user_id), "usuario")
    return _issue_tokens(db, user, organization_id, client, session=session)


# --- Recuperación de contraseña ----------------------------------------------------------


def request_password_reset(db: AppSession, email: str) -> Email | None:
    """Siempre "funciona" para quien llama: no revela si el email existe."""
    user = find_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    settings = get_settings()
    raw = new_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash(raw),
            expires_at=utcnow() + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    link = f"{settings.app_base_url}/reset-password/{raw}"
    return Email(
        to=user.email,
        subject="Restablecer tu contraseña",
        text=(
            f"Hola {user.name}:\n\nPara elegir una contraseña nueva entrá a:\n{link}\n\n"
            f"El link vence en {settings.password_reset_ttl_minutes} minutos. "
            "Si no lo pediste, ignorá este mensaje."
        ),
        template="password_reset",
    )


def confirm_password_reset(db: AppSession, raw_token: str, password: str) -> None:
    token = db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash(raw_token))
        .with_for_update()
    ).scalar_one_or_none()
    now = utcnow()
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise AppError(400, "reset_token_invalid", "El link no es válido o ya venció")
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise AppError(400, "reset_token_invalid", "El link no es válido o ya venció")
    token.used_at = now
    user.password_hash = hash_password(password)
    # Cambiar la contraseña cierra todas las sesiones abiertas.
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason="password_changed")
    )


# --- Invitaciones ------------------------------------------------------------------------


def create_invitation(
    db: AppSession,
    organization_id: UUID,
    email: str,
    role: Role,
    invited_by_membership_id: UUID | None,
) -> tuple[Invitation, Email, str]:
    """Requiere contexto de la organización. Revoca invitaciones pendientes al mismo email.

    Devuelve también el path con el token (``/invite/...``): es la única vez que existe en
    claro (en la base queda el hash). Sin email configurado, quien invita lo comparte a mano.
    """
    settings = get_settings()
    now = utcnow()
    normalized = email.strip().lower()
    db.execute(
        update(Invitation)
        .where(
            Invitation.organization_id == organization_id,
            func.lower(Invitation.email) == normalized,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    raw = new_token()
    invitation = Invitation(
        organization_id=organization_id,
        email=normalized,
        role=role.value,
        token_hash=token_hash(raw),
        invited_by_membership_id=invited_by_membership_id,
        expires_at=now + timedelta(hours=settings.invitation_ttl_hours),
    )
    db.add(invitation)
    org = db.get(Organization, organization_id)
    org_name = org.name if org else "la organización"
    path = f"/invite/{raw}"
    link = f"{settings.app_base_url}{path}"
    message = Email(
        to=normalized,
        subject=f"Te invitaron a {org_name}",
        text=(
            f"Te invitaron a sumarte a {org_name}.\n\nPara aceptar entrá a:\n{link}\n\n"
            f"La invitación vence en {settings.invitation_ttl_hours} horas."
        ),
        template="invitation",
    )
    db.flush()
    return invitation, message, path


def _pending_invitation(db: AppSession, raw_token: str) -> Invitation:
    hashed = token_hash(raw_token)
    # 1) Con solo el hash como capacidad se averigua la organización (política FOR SELECT).
    set_context(db, DbContext(token_hash=hashed))
    org_id = db.execute(
        select(Invitation.organization_id).where(Invitation.token_hash == hashed)
    ).scalar_one_or_none()
    invitation = None
    if org_id is not None:
        # 2) Ya con contexto de la org, se bloquea la fila (FOR UPDATE exige la política de
        #    tenant, no alcanza la de lectura por token).
        set_context(db, DbContext(organization_id=org_id, token_hash=hashed))
        invitation = db.execute(
            select(Invitation).where(Invitation.token_hash == hashed).with_for_update()
        ).scalar_one_or_none()
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= utcnow()
    ):
        raise AppError(404, "invitation_invalid", "La invitación no es válida o ya venció")
    return invitation


def preview_invitation(db: AppSession, raw_token: str) -> tuple[Invitation, str, bool]:
    invitation = _pending_invitation(db, raw_token)
    org = ensure(db.get(Organization, invitation.organization_id), "organización")
    return invitation, org.name, find_user_by_email(db, invitation.email) is not None


def accept_invitation(
    db: AppSession, raw_token: str, password: str, name: str | None, client: ClientInfo
) -> IssuedTokens:
    invitation = _pending_invitation(db, raw_token)
    user = find_user_by_email(db, invitation.email)
    if user is not None:
        if not user.is_active or not verify_password(user.password_hash, password):
            raise _unauthorized("invalid_credentials", "Contraseña incorrecta")
    else:
        if not name:
            raise AppError(422, "name_required", "Indicá tu nombre")
        user = User(
            email=invitation.email, name=name.strip(), password_hash=hash_password(password)
        )
        db.add(user)
        db.flush()

    org_id = invitation.organization_id
    set_context(db, DbContext(organization_id=org_id, user_id=user.id))
    membership = db.execute(
        select(Membership).where(
            Membership.organization_id == org_id, Membership.user_id == user.id
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = Membership(organization_id=org_id, user_id=user.id, role=invitation.role)
        db.add(membership)
    elif membership.status != MembershipStatus.ACTIVE:
        membership.status = MembershipStatus.ACTIVE.value
        membership.role = invitation.role
    invitation.accepted_at = utcnow()
    user.last_login_at = utcnow()
    db.flush()
    record(
        db,
        organization_id=org_id,
        action="membership.joined",
        entity_type="membership",
        entity_id=membership.id,
        actor_user_id=user.id,
        actor_type=ActorType.PUBLIC_TOKEN,
        after={"role": membership.role, "invitation_id": str(invitation.id)},
        ip=client.ip,
        user_agent=client.user_agent,
    )
    return _issue_tokens(db, user, org_id, client)
