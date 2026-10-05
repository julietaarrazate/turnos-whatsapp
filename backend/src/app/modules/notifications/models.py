from datetime import datetime

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class OutboundMessage(IdMixin, Base):
    """Registro de emails enviados. Tabla de sistema (sin tenant).

    No guarda el cuerpo: los emails de invitación y reset llevan tokens secretos.
    """

    __tablename__ = "outbound_messages"

    to_email: Mapped[str] = mapped_column(String(320))
    template: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16))  # SENT | FAILED
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
