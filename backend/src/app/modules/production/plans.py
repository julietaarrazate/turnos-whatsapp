"""Planos de una pieza, con versiones: producción sube "Plano de corte" y, si cambia, sube otro con
el mismo título (v2, v3…). El taller ve siempre la vigente; las anteriores quedan para consultar."""

from collections import defaultdict
from uuid import UUID

from fastapi import Response
from sqlalchemy import func, select

from app.core.db import AppSession
from app.core.errors import not_found
from app.modules.auth import TenantContext
from app.modules.documents import (
    Document,
    DocumentKind,
    DocumentUploadIn,
    file_response,
    get_document,
    upload_file,
)
from app.modules.identity import User
from app.modules.production.models import EventPiece, PiecePlan
from app.modules.production.schemas import PlanIn, PlanOut, PlanRef
from app.modules.production.service import _audit, _editable_event
from app.modules.production.updates import visible_piece


def _plans(db: AppSession, ctx: TenantContext, piece_id: UUID) -> list[PlanOut]:
    rows = db.execute(
        select(PiecePlan, Document.filename, Document.mime, User.name)
        .join(Document, Document.id == PiecePlan.document_id)
        .join(User, User.id == PiecePlan.uploaded_by)
        .where(PiecePlan.piece_id == piece_id, PiecePlan.organization_id == ctx.organization_id)
        .order_by(PiecePlan.title, PiecePlan.version.desc())
    ).all()
    latest: dict[str, int] = {}
    for plan, *_ in rows:
        latest[plan.title] = max(latest.get(plan.title, 0), plan.version)
    return [
        PlanOut(
            id=plan.id,
            piece_id=plan.piece_id,
            title=plan.title,
            version=plan.version,
            current=plan.version == latest[plan.title],
            filename=filename,
            mime=mime,
            uploaded_by_name=author,
            created_at=plan.created_at,
        )
        for plan, filename, mime, author in rows
    ]


def list_plans(db: AppSession, ctx: TenantContext, piece_id: UUID) -> list[PlanOut]:
    piece = visible_piece(db, ctx, piece_id)
    return _plans(db, ctx, piece.id)


def add_plan(db: AppSession, ctx: TenantContext, piece_id: UUID, body: PlanIn) -> PlanOut:
    piece = db.execute(
        select(EventPiece)
        .where(EventPiece.id == piece_id, EventPiece.organization_id == ctx.organization_id)
        .with_for_update()  # dos subidas a la vez no sacan el mismo número de versión
    ).scalar_one_or_none()
    if piece is None:
        raise not_found()
    _editable_event(db, ctx, piece.event_id)
    title = " ".join(body.title.split())
    last = db.execute(
        select(func.max(PiecePlan.version)).where(
            PiecePlan.piece_id == piece.id,
            PiecePlan.organization_id == ctx.organization_id,
            func.lower(PiecePlan.title) == title.lower(),
        )
    ).scalar_one()
    if last:
        # Se respeta cómo se escribió la primera vez ("Plano de corte" y "plano de corte" son uno).
        title = db.execute(
            select(PiecePlan.title)
            .where(
                PiecePlan.piece_id == piece.id,
                PiecePlan.organization_id == ctx.organization_id,
                func.lower(PiecePlan.title) == title.lower(),
            )
            .limit(1)
        ).scalar_one()
    upload = DocumentUploadIn(filename=body.filename, file_base64=body.file_base64)
    document = upload_file(db, ctx, DocumentKind.PIECE_PLAN, upload)
    plan = PiecePlan(
        organization_id=ctx.organization_id,
        event_id=piece.event_id,
        piece_id=piece.id,
        title=title,
        version=(last or 0) + 1,
        document_id=document.id,
        uploaded_by=ctx.user_id,
    )
    db.add(plan)
    db.flush()
    _audit(
        db,
        ctx,
        "piece.plan_uploaded",
        piece.event_id,
        after={"piece": piece.name, "title": title, "version": plan.version},
    )
    return next(p for p in _plans(db, ctx, piece.id) if p.id == plan.id)


def plan_file(db: AppSession, ctx: TenantContext, plan_id: UUID) -> Response:
    plan = db.execute(
        select(PiecePlan).where(
            PiecePlan.id == plan_id, PiecePlan.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if plan is None:
        raise not_found()
    visible_piece(db, ctx, plan.piece_id)
    return file_response(
        get_document(db, ctx.organization_id, plan.document_id, DocumentKind.PIECE_PLAN)
    )


def current_plans(
    db: AppSession, organization_id: UUID, piece_ids: list[UUID]
) -> dict[UUID, list[PlanRef]]:
    """Los planos vigentes de varias piezas (una consulta), para Mis tareas."""
    if not piece_ids:
        return {}
    rows = db.execute(
        select(PiecePlan.id, PiecePlan.piece_id, PiecePlan.title, PiecePlan.version)
        .where(PiecePlan.organization_id == organization_id, PiecePlan.piece_id.in_(piece_ids))
        .order_by(PiecePlan.piece_id, PiecePlan.title, PiecePlan.version.desc())
    ).all()
    out: dict[UUID, list[PlanRef]] = defaultdict(list)
    seen: set[tuple[UUID, str]] = set()
    for plan_id, piece_id, title, version in rows:
        if (piece_id, title) in seen:
            continue
        seen.add((piece_id, title))
        out[piece_id].append(PlanRef(id=plan_id, title=title, version=version))
    return out
