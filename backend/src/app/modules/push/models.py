from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class PushSubscription(IdMixin, Base):
    """Un teléfono o compu que aceptó recibir avisos. Global del usuario (como las sesiones):
    los avisos de cada organización se filtran al mandar, según sus membresías."""

    __tablename__ = "push_subscriptions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_sent_at: Mapped[datetime | None]


class PushKeys(Base):
    """Las claves con las que el servidor firma los avisos (VAPID). Se crean solas la primera
    vez: no hay que configurar nada. Una sola fila."""

    __tablename__ = "push_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    private_pem: Mapped[str] = mapped_column(Text)
    public_key: Mapped[str] = mapped_column(String(200))  # applicationServerKey (base64url)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
