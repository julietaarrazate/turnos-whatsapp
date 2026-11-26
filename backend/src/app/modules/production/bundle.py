"""Descargar todo el evento en un .zip, ordenado en carpetas, para guardarlo al cerrar.

Lo arma en un archivo temporal (en memoria hasta 32 MB, después en disco) y lo manda por partes:
el servidor gratuito tiene poca memoria. Las fotos y los PDF ya vienen comprimidos, así que se
guardan tal cual (más rápido); los links van en un .txt.
"""

import re
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterator
from typing import IO
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.db import AppSession
from app.core.errors import AppError
from app.core.permissions import Permission
from app.core.security import utcnow
from app.core.storage import require_storage
from app.modules.auth import TenantContext
from app.modules.documents import Document
from app.modules.events import get_event
from app.modules.finance import Expense
from app.modules.production.models import EventFile, EventPiece, PiecePlan, PieceProgress

AR = ZoneInfo("America/Argentina/Buenos_Aires")
MAX_BUNDLE_BYTES = 1024 * 1024 * 1024  # 1 GB: más que eso, conviene bajarlo por partes
CHUNK = 1024 * 1024

FOLDERS = {
    "CLIENT": "01 Del cliente",
    "DESIGN": "02 Diseño",
    "PLANS": "03 Planos",
    "PROGRESS": "04 Avances",
    "ADMIN": "05 Administración",
    "OTHER": "06 Otros",
    "RECEIPTS": "07 Comprobantes",
}


def safe_name(text: str, limit: int = 80) -> str:
    """Un nombre que anda en Windows, Mac y el teléfono: sin barras ni caracteres raros."""
    clean = unicodedata.normalize("NFC", text)
    clean = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    return clean[:limit].rstrip(" .") or "archivo"


def _ext(filename: str, mime: str) -> str:
    match = re.search(r"\.([A-Za-z0-9]{1,5})$", filename)
    if match:
        return match.group(1).lower()
    return {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get(mime, "bin")


class _Names:
    """Evita dos archivos con el mismo nombre en la misma carpeta (agrega " (2)")."""

    def __init__(self) -> None:
        self.used: set[str] = set()

    def take(self, folder: str, stem: str, ext: str) -> str:
        candidate, n = f"{folder}/{stem}.{ext}", 2
        while candidate.lower() in self.used:
            candidate, n = f"{folder}/{stem} ({n}).{ext}", n + 1
        self.used.add(candidate.lower())
        return candidate


def _entries(
    db: AppSession, ctx: TenantContext, event_id: UUID
) -> tuple[list[tuple[str, Document]], list[str]]:
    """(ruta en el zip, documento) y las líneas del .txt de links."""
    org = ctx.organization_id
    names = _Names()
    files: list[tuple[str, Document]] = []
    links: list[str] = []
    pieces = dict(
        db.execute(
            select(EventPiece.id, EventPiece.name).where(
                EventPiece.organization_id == org, EventPiece.event_id == event_id
            )
        ).all()
    )

    uploaded = db.execute(
        select(EventFile, Document)
        .outerjoin(Document, Document.id == EventFile.document_id)
        .where(EventFile.organization_id == org, EventFile.event_id == event_id)
        .order_by(EventFile.created_at)
    ).all()
    for row, document in uploaded:
        folder = FOLDERS.get(row.category, FOLDERS["OTHER"])
        if document is None:
            piece = f" ({pieces[row.piece_id]})" if row.piece_id in pieces else ""
            links.append(f"[{folder[3:]}] {row.title}{piece}\n    {row.url}")
            continue
        stem = safe_name(row.title)
        files.append((names.take(folder, stem, _ext(document.filename, document.mime)), document))

    plans = db.execute(
        select(PiecePlan, Document)
        .join(Document, Document.id == PiecePlan.document_id)
        .where(PiecePlan.organization_id == org, PiecePlan.event_id == event_id)
        .order_by(PiecePlan.piece_id, PiecePlan.title, PiecePlan.version)
    ).all()
    for plan, document in plans:
        piece = safe_name(pieces.get(plan.piece_id, "Pieza"), 50)
        stem = f"{safe_name(plan.title, 60)} v{plan.version}"
        files.append(
            (
                names.take(
                    f"{FOLDERS['PLANS']}/{piece}", stem, _ext(document.filename, document.mime)
                ),
                document,
            )
        )

    photos = db.execute(
        select(PieceProgress, Document)
        .join(Document, Document.id == PieceProgress.photo_document_id)
        .where(PieceProgress.organization_id == org, PieceProgress.event_id == event_id)
        .order_by(PieceProgress.created_at)
    ).all()
    for update, document in photos:
        piece = safe_name(pieces.get(update.piece_id, "Pieza"), 50)
        stem = f"{update.created_at.astimezone(AR):%Y-%m-%d %H.%M} {piece}"
        files.append(
            (
                names.take(FOLDERS["PROGRESS"], stem, _ext(document.filename, document.mime)),
                document,
            )
        )

    # Los comprobantes son costos: solo para quien ve costos.
    if ctx.can(Permission.COST_VIEW):
        receipts = db.execute(
            select(Expense, Document)
            .join(Document, Document.id == Expense.receipt_document_id)
            .where(Expense.organization_id == org, Expense.event_id == event_id)
            .order_by(Expense.expense_date)
        ).all()
        for expense, document in receipts:
            stem = f"{expense.expense_date:%Y-%m-%d} {safe_name(expense.description, 60)}"
            files.append(
                (
                    names.take(FOLDERS["RECEIPTS"], stem, _ext(document.filename, document.mime)),
                    document,
                )
            )
    return files, links


def _readme(event_name: str, number: int, links: list[str]) -> str:
    today = utcnow().astimezone(AR)
    text = f"Evento #{number} · {event_name}\nDescargado de Handie el {today:%d/%m/%Y}.\n"
    if links:
        text += (
            "\nLinks del evento (no se descargan: están en Drive, Dropbox, etc.)\n\n"
            + "\n".join(links)
            + "\n"
        )
    return text


def _stream(handle: IO[bytes]) -> Iterator[bytes]:
    try:
        handle.seek(0)
        while chunk := handle.read(CHUNK):
            yield chunk
    finally:
        handle.close()


def download(db: AppSession, ctx: TenantContext, event_id: UUID) -> StreamingResponse:
    event = get_event(db, ctx, event_id)
    files, links = _entries(db, ctx, event_id)
    if sum(document.size for _, document in files) > MAX_BUNDLE_BYTES:
        raise AppError(
            413, "bundle_too_large", "El evento pesa más de 1 GB: bajá los archivos por carpeta"
        )
    handle = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)  # noqa: SIM115 - lo cierra _stream
    with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr("Léeme.txt", _readme(event.name, event.number, links), zipfile.ZIP_DEFLATED)
        if files:
            storage = require_storage()
            for path, document in files:
                bundle.writestr(path, storage.get(document.storage_key))
    name = f"Evento {event.number} - {safe_name(event.name, 60)}.zip"
    ascii_name = name.encode("ascii", "ignore").decode() or "evento.zip"
    return StreamingResponse(
        _stream(handle),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
