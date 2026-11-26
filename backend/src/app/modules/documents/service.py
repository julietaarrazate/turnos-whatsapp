"""Subir y descargar archivos (comprobantes y OC).

El archivo se valida antes de guardarse: tamaño (≤ 10 MB) y tipo por sus primeros bytes, nunca
por la extensión ni por el content-type que declara el navegador. Se descarga con ese tipo y
``nosniff``, así un archivo subido no puede ejecutarse como HTML en el dominio de la app.
"""

import binascii
import hashlib
from base64 import b64decode
from datetime import date, datetime, time
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Response
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.core.ids import uuid7
from app.core.rate_limit import enforce
from app.core.storage import get_storage, require_storage
from app.modules.audit import record
from app.modules.auth import TenantContext
from app.modules.documents.models import Document, DocumentKind
from app.modules.documents.schemas import DocumentOut, DocumentUploadIn

AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _today_ar() -> date:
    return datetime.now(AR_TZ).date()


MAX_BYTES = 10 * 1024 * 1024
# Planos y archivos del evento: 5 MB alcanzan para un PDF o un render; lo pesado va como link.
_MAX_BY_KIND = {"PIECE_PLAN": 5 * 1024 * 1024, "EVENT_FILE": 5 * 1024 * 1024}


def max_bytes(kind: DocumentKind) -> int:
    return _MAX_BY_KIND.get(kind.value, MAX_BYTES)


MAX_AUDIO_BYTES = 2 * 1024 * 1024  # 1 minuto de voz comprimida pesa ~0,5 MB: sobra margen
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
# Lo que graban los navegadores: Chrome/Android WebM (Opus), Firefox Ogg, Safari/iPhone MP4 (AAC).
_MP4_AUDIO_BRANDS = {b"M4A ", b"mp42", b"isom", b"iso5", b"iso6", b"mp41", b"dash"}


def sniff_audio(data: bytes) -> str | None:
    """El tipo real de una grabación por su firma, o None si no es audio grabado."""
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data[4:8] == b"ftyp" and data[8:12] in _MP4_AUDIO_BRANDS:
        return "audio/mp4"
    return None


def sniff(data: bytes) -> str | None:
    """El tipo real del archivo por su firma, o None si no es una foto o un PDF."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def clean_filename(name: str) -> str:
    """Solo el nombre (sin rutas), sin caracteres de control, ≤ 200 caracteres."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ch.isprintable() and ch not in "\"'").strip()
    return base[:200] or "archivo"


def document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        kind=DocumentKind(document.kind),
        filename=document.filename,
        mime=document.mime,
        size=document.size,
        created_at=document.created_at,
    )


def uploads_enabled() -> bool:
    return get_storage() is not None


def storage_used(db: AppSession, organization_id: UUID) -> int:
    """Bytes que ocupan los archivos de la organización."""
    total = db.execute(
        select(func.coalesce(func.sum(Document.size), 0)).where(
            Document.organization_id == organization_id
        )
    ).scalar_one()
    return int(total)


def storage_quota() -> int:
    return get_settings().storage_quota_bytes


def storage_used_today(db: AppSession, organization_id: UUID) -> int:
    """Bytes subidos hoy (día de Argentina) por la organización."""
    start = datetime.combine(_today_ar(), time.min, tzinfo=AR_TZ)
    total = db.execute(
        select(func.coalesce(func.sum(Document.size), 0)).where(
            Document.organization_id == organization_id, Document.created_at >= start
        )
    ).scalar_one()
    return int(total)


def _check_quota(db: AppSession, organization_id: UUID, size: int) -> None:
    if storage_used_today(db, organization_id) + size > get_settings().storage_daily_bytes:
        raise AppError(
            409,
            "daily_upload_limit",
            "Hoy ya se subió mucho a la app. Para cuidar el espacio, seguí mañana o pegá links "
            "de Drive.",
        )
    if storage_used(db, organization_id) + size > storage_quota():
        raise AppError(
            409,
            "storage_full",
            "Se llenó el espacio de archivos de la organización. Pedile a quien administra que "
            "libere lugar descargando y borrando fotos de eventos cerrados.",
        )


def upload(
    db: AppSession, ctx: TenantContext, kind: DocumentKind, body: DocumentUploadIn
) -> DocumentOut:
    require_storage()  # sin almacenamiento configurado, 503 antes de leer nada
    enforce(f"upload:user:{ctx.user_id}", limit=60, window_seconds=600)
    try:
        data = b64decode(body.file_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AppError(422, "upload_invalid", "El archivo llegó dañado. Probá de nuevo.") from exc
    limit = max_bytes(kind)
    if len(data) > limit:
        raise AppError(
            413,
            "upload_too_large",
            f"El archivo pesa más de {limit // (1024 * 1024)} MB: dejalo en Drive y pegá el link",
        )
    _check_quota(db, ctx.organization_id, len(data))
    mime = sniff(data)
    if mime is None:
        raise AppError(
            415, "upload_unsupported", "Solo se aceptan fotos (JPG, PNG, WEBP o HEIC) o PDF"
        )
    return _store(db, ctx, kind, body.filename, data, mime)


def _store(  # noqa: PLR0917 — interno: lo llaman upload y upload_audio ya validado
    db: AppSession, ctx: TenantContext, kind: DocumentKind, filename: str, data: bytes, mime: str
) -> DocumentOut:
    storage = require_storage()
    document_id = uuid7()
    key = f"{ctx.organization_id}/{kind.value.lower()}/{document_id}"
    # Primero el archivo: si la transacción falla después, queda un objeto huérfano (inocuo);
    # al revés quedaría una fila que apunta a nada.
    storage.put(key, data, mime)
    document = Document(
        id=document_id,
        organization_id=ctx.organization_id,
        kind=kind.value,
        storage_key=key,
        filename=clean_filename(filename),
        mime=mime,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        created_by=ctx.user_id,
    )
    db.add(document)
    db.flush()
    db.refresh(document)
    record(
        db,
        organization_id=ctx.organization_id,
        action="document.uploaded",
        entity_type="document",
        entity_id=document.id,
        actor_user_id=ctx.user_id,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
        after={"kind": kind.value, "filename": document.filename, "size": document.size},
    )
    return document_out(document)


def upload_audio(
    db: AppSession, ctx: TenantContext, kind: DocumentKind, body: DocumentUploadIn
) -> DocumentOut:
    """Una grabación de voz (WebM, Ogg o MP4), ≤ 2 MB. Mismo control que las fotos: el tipo se
    mira en el contenido, el tope de espacio vale igual y se descarga con nosniff."""
    require_storage()  # sin almacenamiento configurado, 503 antes de leer nada
    enforce(f"upload:user:{ctx.user_id}", limit=60, window_seconds=600)
    try:
        data = b64decode(body.file_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AppError(422, "upload_invalid", "El audio llegó dañado. Probá de nuevo.") from exc
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError(413, "upload_too_large", "La nota de voz es muy larga (máximo 1 minuto)")
    _check_quota(db, ctx.organization_id, len(data))
    mime = sniff_audio(data)
    if mime is None:
        raise AppError(415, "upload_unsupported", "No es una grabación de voz")
    return _store(db, ctx, kind, body.filename, data, mime)


def upload_file(
    db: AppSession, ctx: TenantContext, kind: DocumentKind, body: DocumentUploadIn
) -> DocumentOut:
    """Foto o PDF (para quien lo usa desde otro módulo)."""
    return upload(db, ctx, kind, body)


def upload_image(
    db: AppSession, ctx: TenantContext, kind: DocumentKind, body: DocumentUploadIn
) -> DocumentOut:
    """Como ``upload`` pero solo fotos (sin PDF): lo que se muestra en una galería."""
    try:
        head = b64decode(body.file_base64[:64], validate=False)
    except (binascii.Error, ValueError):
        head = b""
    if (sniff(head) or "").startswith("application/"):
        raise AppError(415, "upload_unsupported", "Solo se aceptan fotos (JPG, PNG, WEBP o HEIC)")
    return upload(db, ctx, kind, body)


def get_document(
    db: AppSession, organization_id: UUID, document_id: UUID, kind: DocumentKind
) -> Document:
    """Un archivo de la organización y del tipo pedido (si no, 404 como cualquier ID ajeno)."""
    document = db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.kind == kind.value,
        )
    ).scalar_one_or_none()
    if document is None:
        raise not_found("document_not_found", "El archivo adjunto no existe")
    return document


def documents_by_id(
    db: AppSession, organization_id: UUID, ids: set[UUID]
) -> dict[UUID, DocumentOut]:
    if not ids:
        return {}
    rows = db.execute(
        select(Document).where(Document.organization_id == organization_id, Document.id.in_(ids))
    ).scalars()
    return {row.id: document_out(row) for row in rows}


def file_response(document: Document) -> Response:
    """El archivo para ver en el navegador (o descargar), sin que se interprete como otra cosa."""
    data = require_storage().get(document.storage_key)
    ascii_name = document.filename.encode("ascii", "ignore").decode() or "archivo"
    disposition = f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(document.filename)}"
    return Response(
        content=data,
        media_type=document.mime,
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )
