"""Crear cuenta: la persona arma su usuario y su productora, que queda esperando aprobación.

Nadie usa la productora hasta que la dueña de la plataforma la aprueba desde el panel; mientras
tanto la sesión existe pero sin organización activa (ningún endpoint de negocio responde).
"""

from uuid import UUID

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import AppSession, DbContext, set_context
from app.core.enums import Role
from app.core.errors import AppError
from app.core.ids import uuid7
from app.core.security import hash_password
from app.modules.audit import record
from app.modules.auth import find_user_by_email
from app.modules.identity import Membership, MembershipStatus, Organization, User
from app.modules.notifications import Email
from app.modules.organizations import provision_organization
from app.modules.platform.schemas import SignupIn

# Freno contra cuentas en masa: con tantas esperando, no se aceptan nuevas hasta revisarlas.
MAX_PENDING_SIGNUPS = 20


def _pending_count(db: AppSession, user_id: UUID | None) -> int:
    set_context(db, DbContext(user_id=user_id, platform_admin=True))
    count = db.scalar(
        select(func.count())
        .select_from(Organization)
        .where(Organization.pending_approval.is_(True), Organization.suspended_at.is_(None))
    )
    set_context(db, DbContext(user_id=user_id))
    return count or 0


def signup(db: AppSession, body: SignupIn) -> tuple[User, list[Email]]:
    if find_user_by_email(db, body.email) is not None:
        raise AppError(
            409,
            "email_taken",
            "Ya hay una cuenta con ese mail. Entrá con tu contraseña o recuperala.",
        )
    if _pending_count(db, None) >= MAX_PENDING_SIGNUPS:
        raise AppError(
            429,
            "signups_paused",
            "Por ahora no estamos tomando cuentas nuevas. Probá de nuevo en unos días.",
        )

    user = User(
        id=uuid7(),
        email=body.email.strip(),
        name=" ".join(body.name.split()),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()

    org_id = uuid7()
    org_name = " ".join(body.organization_name.split())
    set_context(db, DbContext(organization_id=org_id, user_id=user.id))
    db.add(Organization(id=org_id, name=org_name, pending_approval=True))
    db.flush()
    provision_organization(db, org_id)
    db.add(
        Membership(
            organization_id=org_id,
            user_id=user.id,
            role=Role.OWNER.value,
            status=MembershipStatus.ACTIVE.value,
        )
    )
    record(
        db,
        organization_id=org_id,
        action="org.signed_up",
        entity_type="organization",
        entity_id=org_id,
        actor_user_id=user.id,
        after={"name": org_name},
    )
    db.flush()
    set_context(db, DbContext(user_id=user.id))

    settings = get_settings()
    admins = [e.strip() for e in settings.platform_admins.split(",") if e.strip()]
    emails = [
        Email(
            to=admin,
            subject=f"Nueva cuenta en Handie: {org_name}",
            text=(
                f"{user.name} ({user.email}) creó la cuenta de «{org_name}».\n\n"
                f"Queda esperando tu aprobación: {settings.app_base_url}/admin\n"
            ),
            template="platform.signup",
        )
        for admin in admins
    ]
    return user, emails


def approval_email(db: AppSession, organization_id: UUID) -> list[Email]:
    """Aviso a los dueños de la productora recién aprobada (requiere su contexto de tenant)."""
    org = db.get(Organization, organization_id)
    if org is None:
        return []
    owners = db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.role == Role.OWNER.value, Membership.status == MembershipStatus.ACTIVE)
    )
    base = get_settings().app_base_url
    return [
        Email(
            to=owner.email,
            subject="Tu cuenta de Handie está aprobada",
            text=(
                f"Hola {owner.name}: ya podés usar Handie con «{org.name}».\n\n"
                f"Entrá desde {base}/login\n"
            ),
            template="platform.approved",
        )
        for owner in owners
    ]
