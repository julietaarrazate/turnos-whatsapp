from datetime import datetime

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    """Tabla global (sin ``organization_id`` ni RLS): solo se accede desde servicios."""

    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", text("lower(email)"), unique=True),)

    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    last_login_at: Mapped[datetime | None]
    # Bloqueo de pantalla: PIN de 4 dígitos (hash argon2) y los intentos fallidos seguidos.
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    pin_failures: Mapped[int] = mapped_column(default=0, server_default="0")
