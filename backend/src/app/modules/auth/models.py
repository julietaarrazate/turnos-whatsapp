from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, tenant_unique
from app.core.enums import Role, check_in


class AuthSession(IdMixin, Base):
    """Sesión de login (familia de refresh tokens). Tabla global del usuario, sin tenant."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    active_organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    revoked_reason: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))


class RefreshToken(IdMixin, Base):
    __tablename__ = "refresh_tokens"

    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class PasswordResetToken(IdMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class Invitation(IdMixin, Base):
    """Invitación a una organización (tabla tenant con RLS).

    Además de la política de tenant, la fila se puede leer presentando el hash de su token
    (``app.token_hash``): así el invitado, sin sesión, ve solo SU invitación.
    """

    __tablename__ = "invitations"
    __table_args__ = (
        tenant_unique(),
        CheckConstraint(check_in("role", Role), name="role"),
        ForeignKeyConstraint(
            ["organization_id", "invited_by_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_membership_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class Passkey(IdMixin, Base):
    """Llave de acceso (WebAuthn) de un dispositivo: entrar con huella, cara o el bloqueo del
    teléfono, sin mail ni contraseña. Tabla global del usuario, sin tenant (como las sesiones).
    Solo se guarda la clave pública: el secreto nunca sale del dispositivo."""

    __tablename__ = "passkeys"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_used_at: Mapped[datetime | None]


class WebauthnChallenge(IdMixin, Base):
    """Desafío de un solo uso (5 minutos) para registrar una llave o entrar con ella."""

    __tablename__ = "webauthn_challenges"
    __table_args__ = (CheckConstraint("purpose IN ('REGISTER', 'LOGIN')", name="purpose"),)

    challenge_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
