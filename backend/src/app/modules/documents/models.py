from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, tenant_unique
from app.core.enums import check_in


class DocumentKind(StrEnum):
    RECEIPT = "RECEIPT"  # comprobante de un gasto (O-04)
    PURCHASE_ORDER = "PURCHASE_ORDER"  # OC de una aprobación manual (P-06)
    PROGRESS_PHOTO = "PROGRESS_PHOTO"  # foto de avance de una pieza (taller, montaje)
    PIECE_PLAN = "PIECE_PLAN"  # plano o diseño de una pieza (PDF o imagen), con versiones
    VOICE_NOTE = "VOICE_NOTE"  # nota de voz de un avance (≤ 1 minuto)
    EVENT_FILE = "EVENT_FILE"  # archivo del evento: brief, manual de marca, render, permiso…


class Document(IdMixin, Base):
    """Un archivo subido (DOMAIN_MODEL §2.8). Inmutable: el runtime solo puede leer e insertar.

    La entidad dueña lo referencia con una FK compuesta (``expenses.receipt_document_id``,
    ``proposals.po_document_id``) y es la que decide quién puede descargarlo.
    """

    __tablename__ = "documents"
    __table_args__ = (
        tenant_unique(),
        CheckConstraint(check_in("kind", DocumentKind), name="kind"),
        CheckConstraint("size > 0", name="size_positive"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(16))
    storage_key: Mapped[str] = mapped_column(String(200))  # sin datos del usuario
    filename: Mapped[str] = mapped_column(String(200))  # el nombre original, para descargar
    mime: Mapped[str] = mapped_column(String(100))  # detectado por contenido, no declarado
    size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
