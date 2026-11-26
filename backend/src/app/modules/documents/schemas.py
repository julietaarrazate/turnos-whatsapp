from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.documents.models import DocumentKind


class DocumentUploadIn(BaseModel):
    """Un archivo en base64 (como las planillas): foto (JPG, PNG, WEBP, HEIC) o PDF, ≤ 10 MB."""

    filename: str = Field(min_length=1, max_length=255)
    file_base64: str = Field(min_length=4, max_length=14_000_000)


class DocumentOut(BaseModel):
    id: UUID
    kind: DocumentKind
    filename: str
    mime: str
    size: int
    created_at: datetime


class StorageOut(BaseModel):
    """Espacio de archivos de la organización, en bytes. ``enabled`` = hay dónde guardarlos."""

    used: int
    limit: int
    enabled: bool
