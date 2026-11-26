"""Archivos del evento: todo lo del evento en un lugar, ordenado solo.

Junta lo que se sube en la pestaña (del cliente, diseño, administración, otros; archivo o link) con
lo que ya vive en las piezas: los planos con su versión y las fotos de avance. Así nadie arma
carpetas ni busca en Drive "Final2": cada cosa está pegada al evento y, si corresponde, a la pieza.
"""

import unicodedata
from urllib.parse import urlparse
from uuid import UUID

from fastapi import Response
from sqlalchemy import ColumnElement, or_, select

from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.core.permissions import Permission
from app.modules.auth import TenantContext
from app.modules.documents import (
    Document,
    DocumentKind,
    DocumentUploadIn,
    file_response,
    get_document,
    upload_file,
)
from app.modules.events import Event, get_event
from app.modules.identity import User
from app.modules.production.models import (
    EventFile,
    EventPiece,
    ExpectedFile,
    FileCategory,
    PiecePlan,
    PieceProgress,
)
from app.modules.production.schemas import (
    EventFileIn,
    EventFilesOut,
    ExpectedFileIn,
    ExpectedFileOut,
    ExpectedTemplateIn,
    FileEvent,
    FileItem,
)
from app.modules.production.service import _audit, _editable_event

_EXPIRING_HOSTS = ("wetransfer.com", "we.tl")
SEARCH_LIMIT = 30


def _expires_soon(url: str | None) -> bool:
    host = (urlparse(url).hostname or "") if url else ""
    return any(host == h or host.endswith(f".{h}") for h in _EXPIRING_HOSTS)


def _can_edit(ctx: TenantContext) -> bool:
    """Suben y borran archivos producción y lo comercial (el brief llega por ventas)."""
    return ctx.can(Permission.PRODUCTION_MANAGE) or ctx.can(Permission.BUDGET_EDIT)


def _file_event(event: Event) -> FileEvent:
    return FileEvent(id=event.id, number=event.number, name=event.name)


def _uploaded(
    db: AppSession, ctx: TenantContext, where: list[ColumnElement[bool]], limit: int | None = None
) -> list[FileItem]:
    query = (
        select(EventFile, Event, User.name, EventPiece.name, Document.mime)
        .join(Event, Event.id == EventFile.event_id)
        .join(User, User.id == EventFile.created_by)
        .outerjoin(EventPiece, EventPiece.id == EventFile.piece_id)
        .outerjoin(Document, Document.id == EventFile.document_id)
        .where(EventFile.organization_id == ctx.organization_id, *where)
        .order_by(EventFile.created_at.desc())
    )
    if limit:
        query = query.limit(limit)
    editable = _can_edit(ctx)
    rows = db.execute(query).all()
    # Import diferido: approvals importa este módulo (para _can_edit).
    from app.modules.production.approvals import latest_by_file  # noqa: PLC0415

    approvals = latest_by_file(db, ctx.organization_id, [row.id for row, *_ in rows])
    return [
        FileItem(
            id=row.id,
            source="LINK" if row.url else "FILE",
            category=row.category,
            title=row.title,
            piece_id=row.piece_id,
            piece_name=piece,
            href=row.url or f"/api/v1/event-files/{row.id}/file",
            mime=mime,
            version=None,
            current=None,
            expires_soon=_expires_soon(row.url),
            author_name=author,
            created_at=row.created_at,
            event=_file_event(event),
            can_delete=editable,
            approval=approvals.get(row.id),
        )
        for row, event, author, piece, mime in rows
    ]


def _plans(
    db: AppSession, ctx: TenantContext, where: list[ColumnElement[bool]], limit: int | None = None
) -> list[FileItem]:
    query = (
        select(PiecePlan, Event, User.name, EventPiece.name, Document.mime)
        .join(Event, Event.id == PiecePlan.event_id)
        .join(EventPiece, EventPiece.id == PiecePlan.piece_id)
        .join(User, User.id == PiecePlan.uploaded_by)
        .join(Document, Document.id == PiecePlan.document_id)
        .where(PiecePlan.organization_id == ctx.organization_id, *where)
        .order_by(EventPiece.sort, PiecePlan.title, PiecePlan.version.desc())
    )
    if limit:
        query = query.limit(limit)
    rows = db.execute(query).all()
    latest: dict[tuple[UUID, str], int] = {}
    for plan, *_ in rows:
        key = (plan.piece_id, plan.title)
        latest[key] = max(latest.get(key, 0), plan.version)
    return [
        FileItem(
            id=plan.id,
            source="PLAN",
            category="DESIGN",
            title=plan.title,
            piece_id=plan.piece_id,
            piece_name=piece,
            href=f"/api/v1/piece-plans/{plan.id}/file",
            mime=mime,
            version=plan.version,
            current=plan.version == latest[(plan.piece_id, plan.title)],
            expires_soon=False,
            author_name=author,
            created_at=plan.created_at,
            event=_file_event(event),
            can_delete=False,  # los planos no se borran: así se sabe con cuál se fabricó
        )
        for plan, event, author, piece, mime in rows
    ]


def _photos(db: AppSession, ctx: TenantContext, event_id: UUID) -> list[FileItem]:
    rows = db.execute(
        select(PieceProgress, Event, User.name, EventPiece.name)
        .join(Event, Event.id == PieceProgress.event_id)
        .join(EventPiece, EventPiece.id == PieceProgress.piece_id)
        .join(User, User.id == PieceProgress.author_user_id)
        .where(
            PieceProgress.organization_id == ctx.organization_id,
            PieceProgress.event_id == event_id,
            PieceProgress.photo_document_id.is_not(None),
        )
        .order_by(PieceProgress.created_at.desc())
    ).all()
    return [
        FileItem(
            id=update.id,
            source="PHOTO",
            category="PROGRESS",
            title=update.note or f"Avance de {piece}",
            piece_id=update.piece_id,
            piece_name=piece,
            href=f"/api/v1/piece-updates/{update.id}/photo",
            mime="image/jpeg",
            version=None,
            current=None,
            expires_soon=False,
            author_name=author,
            created_at=update.created_at,
            event=_file_event(event),
            can_delete=False,
        )
        for update, event, author, piece in rows
    ]


# Lo que suele pedir cada tipo de trabajo (las listas base; cada evento la ajusta).
_C, _D, _A = FileCategory.CLIENT, FileCategory.DESIGN, FileCategory.ADMIN
TEMPLATES: dict[str, list[tuple[str, FileCategory]]] = {
    "STAND": [
        ("Brief", _C),
        ("Manual de marca", _C),
        ("Logos en vector", _C),
        ("Planimetría del predio", _C),
        ("Reglamento del predio", _A),
        ("Render aprobado", _D),
        ("Plano de corte", _D),
        ("Seguro de responsabilidad civil", _A),
        ("ART del personal", _A),
    ],
    "BTL": [
        ("Brief", _C),
        ("Manual de marca", _C),
        ("Logos en vector", _C),
        ("Guion de la activación", _C),
        ("Render aprobado", _D),
        ("Permiso del lugar", _A),
        ("Seguro de responsabilidad civil", _A),
        ("ART del personal", _A),
    ],
    "EVENT": [
        ("Brief", _C),
        ("Planimetría del lugar", _C),
        ("Cronograma de armado", _C),
        ("Render aprobado", _D),
        ("Permiso del lugar", _A),
        ("Seguro de responsabilidad civil", _A),
        ("ART del personal", _A),
    ],
    "VISUAL": [
        ("Brief", _C),
        ("Manual de marca", _C),
        ("Logos en vector", _C),
        ("Medidas del lugar", _C),
        ("Render aprobado", _D),
        ("Archivo de impresión aprobado", _D),
    ],
}


def normalize(text: str) -> str:
    """Sin acentos, mayúsculas ni espacios de más: "Planimetría  del predio" = "planimetria del
    predio"."""
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return " ".join(plain.lower().split())


def _expected(
    db: AppSession, ctx: TenantContext, event_id: UUID, items: list[FileItem]
) -> list[ExpectedFileOut]:
    titles = [normalize(i.title) for i in items if i.source in {"FILE", "LINK", "PLAN"}]
    rows = db.execute(
        select(ExpectedFile)
        .where(
            ExpectedFile.event_id == event_id, ExpectedFile.organization_id == ctx.organization_id
        )
        .order_by(ExpectedFile.sort, ExpectedFile.title)
    ).scalars()
    out = []
    for row in rows:
        wanted = normalize(row.title)
        out.append(
            ExpectedFileOut(
                id=row.id,
                title=row.title,
                category=FileCategory(row.category),
                present=any(wanted in title for title in titles),
            )
        )
    return out


def list_files(db: AppSession, ctx: TenantContext, event_id: UUID) -> EventFilesOut:
    event = get_event(db, ctx, event_id)
    items = (
        _uploaded(db, ctx, [EventFile.event_id == event.id])
        + _plans(db, ctx, [PiecePlan.event_id == event.id])
        + _photos(db, ctx, event.id)
    )
    return EventFilesOut(
        items=items, expected=_expected(db, ctx, event.id, items), can_edit=_can_edit(ctx)
    )


def _editable_for_files(db: AppSession, ctx: TenantContext, event_id: UUID) -> None:
    if not _can_edit(ctx):
        raise AppError(403, "cannot_edit_files", "Solo producción o comercial editan los archivos")
    event = get_event(db, ctx, event_id)
    _editable_event(db, ctx, event.id)


def _add_expected(
    db: AppSession, ctx: TenantContext, event_id: UUID, title: str, category: FileCategory
) -> bool:
    """Agrega el ítem si no hay uno igual (sin acentos ni mayúsculas). Devuelve si lo agregó."""
    clean = " ".join(title.split())
    existing = db.execute(
        select(ExpectedFile.title).where(
            ExpectedFile.event_id == event_id, ExpectedFile.organization_id == ctx.organization_id
        )
    ).scalars()
    if normalize(clean) in {normalize(t) for t in existing}:
        return False
    last = db.execute(
        select(ExpectedFile.sort)
        .where(
            ExpectedFile.event_id == event_id, ExpectedFile.organization_id == ctx.organization_id
        )
        .order_by(ExpectedFile.sort.desc())
        .limit(1)
    ).scalar_one_or_none()
    db.add(
        ExpectedFile(
            organization_id=ctx.organization_id,
            event_id=event_id,
            title=clean,
            category=category.value,
            sort=(last or 0) + 1,
        )
    )
    db.flush()
    return True


def add_expected(
    db: AppSession, ctx: TenantContext, event_id: UUID, body: ExpectedFileIn
) -> EventFilesOut:
    _editable_for_files(db, ctx, event_id)
    _add_expected(db, ctx, event_id, body.title, body.category)
    return list_files(db, ctx, event_id)


def apply_template(
    db: AppSession, ctx: TenantContext, event_id: UUID, body: ExpectedTemplateIn
) -> EventFilesOut:
    """Suma la lista base del tipo de evento (lo que ya estaba no se repite)."""
    _editable_for_files(db, ctx, event_id)
    added = sum(
        _add_expected(db, ctx, event_id, title, category)
        for title, category in TEMPLATES[body.template]
    )
    _audit(
        db,
        ctx,
        "event.expected_files_set",
        event_id,
        after={"template": body.template, "added": added},
    )
    return list_files(db, ctx, event_id)


def delete_expected(db: AppSession, ctx: TenantContext, expected_id: UUID) -> None:
    row = db.execute(
        select(ExpectedFile).where(
            ExpectedFile.id == expected_id, ExpectedFile.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    _editable_for_files(db, ctx, row.event_id)
    db.delete(row)
    db.flush()


def _check_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise AppError(422, "link_invalid", "El link tiene que empezar con https://")
    return url


def add_file(db: AppSession, ctx: TenantContext, event_id: UUID, body: EventFileIn) -> FileItem:
    if not _can_edit(ctx):
        raise AppError(403, "cannot_edit_files", "Solo producción o comercial suben archivos")
    event = get_event(db, ctx, event_id)
    _editable_event(db, ctx, event.id)
    if (body.url is None) == (body.file is None):
        raise AppError(422, "file_or_link", "Subí un archivo o pegá un link (uno de los dos)")
    if body.piece_id is not None:
        piece = db.execute(
            select(EventPiece.id).where(
                EventPiece.id == body.piece_id,
                EventPiece.organization_id == ctx.organization_id,
                EventPiece.event_id == event.id,
            )
        ).scalar_one_or_none()
        if piece is None:
            raise AppError(422, "piece_not_in_event", "La pieza no es de este evento")
    url = _check_url(body.url) if body.url is not None else None
    document_id = None
    if body.file is not None:
        upload = DocumentUploadIn(filename=body.file.filename, file_base64=body.file.file_base64)
        document_id = upload_file(db, ctx, DocumentKind.EVENT_FILE, upload).id
    row = EventFile(
        organization_id=ctx.organization_id,
        event_id=event.id,
        piece_id=body.piece_id,
        category=body.category.value,
        title=" ".join(body.title.split()),
        document_id=document_id,
        url=url,
        created_by=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        ctx,
        "event.file_added",
        event.id,
        after={"title": row.title, "category": row.category, "link": url is not None},
    )
    return next(i for i in _uploaded(db, ctx, [EventFile.id == row.id]))


def _row(db: AppSession, ctx: TenantContext, file_id: UUID) -> EventFile:
    row = db.execute(
        select(EventFile).where(
            EventFile.id == file_id, EventFile.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row


def delete_file(db: AppSession, ctx: TenantContext, file_id: UUID) -> None:
    """Saca el archivo o link de la pestaña. El archivo subido queda guardado (los documentos
    no se borran) y el borrado queda en la auditoría."""
    if not _can_edit(ctx):
        raise AppError(403, "cannot_edit_files", "Solo producción o comercial borran archivos")
    row = _row(db, ctx, file_id)
    _editable_event(db, ctx, row.event_id)
    _audit(db, ctx, "event.file_removed", row.event_id, before={"title": row.title})
    db.delete(row)
    db.flush()


def open_file(db: AppSession, ctx: TenantContext, file_id: UUID) -> Response:
    row = _row(db, ctx, file_id)
    get_event(db, ctx, row.event_id)  # el evento tiene que estar a la vista
    if row.document_id is None:
        raise not_found()  # un link se abre directo, no pasa por acá
    return file_response(
        get_document(db, ctx.organization_id, row.document_id, DocumentKind.EVENT_FILE)
    )


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search(db: AppSession, ctx: TenantContext, q: str) -> list[FileItem]:
    """Busca por título del archivo, de la pieza o del evento, en todos los eventos."""
    words = q.split()
    if not words or len(q.strip()) < 2:
        return []
    uploaded_where: list[ColumnElement[bool]] = [Event.deleted_at.is_(None)]
    plan_where: list[ColumnElement[bool]] = [Event.deleted_at.is_(None)]
    for word in words[:5]:
        pattern = _like(word)
        uploaded_where.append(
            or_(
                EventFile.title.ilike(pattern, escape="\\"),
                EventPiece.name.ilike(pattern, escape="\\"),
                Event.name.ilike(pattern, escape="\\"),
            )
        )
        plan_where.append(
            or_(
                PiecePlan.title.ilike(pattern, escape="\\"),
                EventPiece.name.ilike(pattern, escape="\\"),
                Event.name.ilike(pattern, escape="\\"),
            )
        )
    found = _uploaded(db, ctx, uploaded_where, SEARCH_LIMIT) + [
        p for p in _plans(db, ctx, plan_where, SEARCH_LIMIT) if p.current
    ]
    found.sort(key=lambda item: item.created_at, reverse=True)
    return found[:SEARCH_LIMIT]


__all__ = ["FileCategory", "add_file", "delete_file", "list_files", "open_file", "search"]
