"""Avances de una pieza: quien la hace sube una foto y/o una nota ("letras cortadas, mañana
cableado"). Los ve quien ve el evento y quien tiene la pieza asignada (taller/montaje)."""

from uuid import UUID

from fastapi import Response
from sqlalchemy import select

from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.core.permissions import Permission
from app.modules.auth import TenantContext
from app.modules.documents import (
    DocumentKind,
    DocumentUploadIn,
    file_response,
    get_document,
    upload_audio,
    upload_image,
)
from app.modules.identity import User
from app.modules.production.models import EventPiece, PieceProgress
from app.modules.production.schemas import PieceUpdateIn, PieceUpdateOut
from app.modules.production.service import _audit, _editable_event


def visible_piece(db: AppSession, ctx: TenantContext, piece_id: UUID) -> EventPiece:
    """La pieza, si quien consulta puede verla: ve el evento, o la tiene asignada. Si no, 404."""
    piece = db.execute(
        select(EventPiece).where(
            EventPiece.id == piece_id, EventPiece.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if piece is None:
        raise not_found()
    if not ctx.can(Permission.ORG_VIEW) and piece.assignee_user_id != ctx.user_id:
        raise not_found()
    return piece


def _can_post(ctx: TenantContext, piece: EventPiece) -> bool:
    return ctx.can(Permission.PRODUCTION_MANAGE) or piece.assignee_user_id == ctx.user_id


def _out(update: PieceProgress, author: str) -> PieceUpdateOut:
    return PieceUpdateOut(
        id=update.id,
        piece_id=update.piece_id,
        author_name=author,
        note=update.note,
        has_photo=update.photo_document_id is not None,
        has_audio=update.audio_document_id is not None,
        created_at=update.created_at,
    )


def list_updates(db: AppSession, ctx: TenantContext, piece_id: UUID) -> list[PieceUpdateOut]:
    piece = visible_piece(db, ctx, piece_id)
    rows = db.execute(
        select(PieceProgress, User.name)
        .join(User, User.id == PieceProgress.author_user_id)
        .where(
            PieceProgress.piece_id == piece.id,
            PieceProgress.organization_id == ctx.organization_id,
        )
        .order_by(PieceProgress.created_at.desc(), PieceProgress.id.desc())
    ).all()
    return [_out(update, name) for update, name in rows]


def add_update(
    db: AppSession, ctx: TenantContext, piece_id: UUID, body: PieceUpdateIn
) -> PieceUpdateOut:
    piece = visible_piece(db, ctx, piece_id)
    if not _can_post(ctx, piece):
        # Ve el evento pero no es de producción ni tiene la pieza: no sube avances.
        raise AppError(403, "not_assigned", "Solo producción o quien tiene la pieza suben avances")
    _editable_event(db, ctx, piece.event_id)
    note = (body.note or "").strip() or None
    if note is None and body.photo is None and body.audio is None:
        raise AppError(422, "update_empty", "Sacá una foto, grabá una nota de voz o escribí")
    photo_id = None
    if body.photo is not None:
        upload = DocumentUploadIn(filename=body.photo.filename, file_base64=body.photo.file_base64)
        photo_id = upload_image(db, ctx, DocumentKind.PROGRESS_PHOTO, upload).id
    audio_id = None
    if body.audio is not None:
        voice = DocumentUploadIn(filename=body.audio.filename, file_base64=body.audio.file_base64)
        audio_id = upload_audio(db, ctx, DocumentKind.VOICE_NOTE, voice).id
    update = PieceProgress(
        organization_id=ctx.organization_id,
        event_id=piece.event_id,
        piece_id=piece.id,
        author_user_id=ctx.user_id,
        note=note,
        photo_document_id=photo_id,
        audio_document_id=audio_id,
    )
    db.add(update)
    db.flush()
    db.refresh(update)
    _audit(
        db,
        ctx,
        "piece.update_posted",
        piece.event_id,
        after={
            "piece": piece.name,
            "photo": photo_id is not None,
            "audio": audio_id is not None,
            "update_id": str(update.id),
            "note": note[:140] if note else None,
        },
    )
    author = db.execute(select(User.name).where(User.id == ctx.user_id)).scalar_one()
    return _out(update, author)


def update_photo(db: AppSession, ctx: TenantContext, update_id: UUID) -> Response:
    update = db.execute(
        select(PieceProgress).where(
            PieceProgress.id == update_id, PieceProgress.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if update is None or update.photo_document_id is None:
        raise not_found()
    visible_piece(db, ctx, update.piece_id)
    document = get_document(
        db, ctx.organization_id, update.photo_document_id, DocumentKind.PROGRESS_PHOTO
    )
    return file_response(document)


def update_audio(db: AppSession, ctx: TenantContext, update_id: UUID) -> Response:
    update = db.execute(
        select(PieceProgress).where(
            PieceProgress.id == update_id, PieceProgress.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if update is None or update.audio_document_id is None:
        raise not_found()
    visible_piece(db, ctx, update.piece_id)
    document = get_document(
        db, ctx.organization_id, update.audio_document_id, DocumentKind.VOICE_NOTE
    )
    return file_response(document)
