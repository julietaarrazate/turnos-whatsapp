from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.core.rate_limit import enforce
from app.modules.auth import Client, Public, TenantContext, require
from app.modules.production import (
    activity,
    approvals,
    bundle,
    files,
    my_work,
    pieces,
    plans,
    service,
    updates,
    venues,
)
from app.modules.production.schemas import (
    ActivityPage,
    ActivitySeenIn,
    ApprovalDecisionIn,
    ApprovalLinkOut,
    EventFileIn,
    EventFilesOut,
    EventSupplierOut,
    EventSupplierUpdate,
    EventVenueOut,
    ExpectedFileIn,
    ExpectedTemplateIn,
    FileItem,
    MyPieceUpdate,
    MyTaskUpdate,
    MyWorkOut,
    OpenPiece,
    PieceIn,
    PieceOut,
    PiecesOut,
    PieceUpdate,
    PieceUpdateIn,
    PieceUpdateOut,
    PlanIn,
    PlanOut,
    ProductionOut,
    PublicApproval,
    TaskIn,
    TaskOut,
    TaskUpdate,
    UnreadOut,
    VenueSheetIn,
)

router = APIRouter(prefix="/api/v1", tags=["production"])
public_router = APIRouter(prefix="/api/v1/public", tags=["public"])
Token = Annotated[str, Path(min_length=20, max_length=100)]

View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Manage = Annotated[TenantContext, Depends(require(Permission.PRODUCTION_MANAGE))]
OwnWork = Annotated[TenantContext, Depends(require(Permission.WORK_OWN))]


@router.post("/events/{event_id}/start-production")
def start_production(event_id: UUID, ctx: Manage, db: DbSession) -> ProductionOut:
    """Iniciar producción (APPROVED → IN_PRODUCTION): arma la lista de contratación por
    proveedor desde la versión aceptada y las tareas sugeridas."""
    return service.start(db, ctx, event_id)


@router.get("/events/{event_id}/production")
def get_production(event_id: UUID, ctx: View, db: DbSession) -> ProductionOut:
    return service.production(db, ctx, event_id)


@router.patch("/event-suppliers/{event_supplier_id}")
def update_supplier(
    event_supplier_id: UUID, body: EventSupplierUpdate, ctx: Manage, db: DbSession
) -> EventSupplierOut:
    """Marcar un proveedor como confirmado o cancelado, o anotar algo."""
    return service.update_supplier(db, ctx, event_supplier_id, body)


@router.post("/events/{event_id}/tasks", status_code=status.HTTP_201_CREATED)
def add_task(event_id: UUID, body: TaskIn, ctx: Manage, db: DbSession) -> TaskOut:
    return service.add_task(db, ctx, event_id, body)


@router.patch("/tasks/{task_id}")
def update_task(task_id: UUID, body: TaskUpdate, ctx: Manage, db: DbSession) -> TaskOut:
    return service.update_task(db, ctx, task_id, body)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: UUID, ctx: Manage, db: DbSession) -> None:
    service.delete_task(db, ctx, task_id)


@router.get("/events/{event_id}/pieces")
def list_pieces(event_id: UUID, ctx: View, db: DbSession) -> PiecesOut:
    """Las piezas a medida del evento y su avance (% promedio de fases, cuántas listas)."""
    return pieces.list_pieces(db, ctx, event_id)


@router.post("/events/{event_id}/pieces", status_code=status.HTTP_201_CREATED)
def add_piece(event_id: UUID, body: PieceIn, ctx: Manage, db: DbSession) -> PieceOut:
    return pieces.add_piece(db, ctx, event_id, body)


@router.patch("/pieces/{piece_id}")
def update_piece(piece_id: UUID, body: PieceUpdate, ctx: Manage, db: DbSession) -> PieceOut:
    """Cambiar la fase (diseño → a comprar → taller → listo → montado, o volver), el responsable…"""
    return pieces.update_piece(db, ctx, piece_id, body)


@router.delete("/pieces/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_piece(piece_id: UUID, ctx: Manage, db: DbSession) -> None:
    pieces.delete_piece(db, ctx, piece_id)


@router.get("/my-work")
def get_my_work(ctx: OwnWork, db: DbSession) -> MyWorkOut:
    """Mis tareas: piezas y tareas asignadas a quien consulta, pendientes, en eventos abiertos."""
    return my_work.my_work(db, ctx)


@router.patch("/my-work/pieces/{piece_id}")
def move_my_piece(piece_id: UUID, body: MyPieceUpdate, ctx: OwnWork, db: DbSession) -> PieceOut:
    """Cambiar la fase de una pieza propia. La de otra persona responde 404."""
    return my_work.move_my_piece(db, ctx, piece_id, body.status)


@router.patch("/my-work/tasks/{task_id}")
def move_my_task(task_id: UUID, body: MyTaskUpdate, ctx: OwnWork, db: DbSession) -> TaskOut:
    """Marcar una tarea propia en curso o hecha. La de otra persona responde 404."""
    return my_work.move_my_task(db, ctx, task_id, body.status)


@router.get("/pieces/{piece_id}/updates")
def list_piece_updates(piece_id: UUID, ctx: OwnWork, db: DbSession) -> list[PieceUpdateOut]:
    """Los avances de la pieza (lo más nuevo primero). Los ve quien ve el evento o la tiene."""
    return updates.list_updates(db, ctx, piece_id)


@router.post("/pieces/{piece_id}/updates", status_code=status.HTTP_201_CREATED)
def add_piece_update(
    piece_id: UUID, body: PieceUpdateIn, ctx: OwnWork, db: DbSession
) -> PieceUpdateOut:
    """Subir un avance: foto y/o nota. Producción, o quien tiene la pieza asignada."""
    return updates.add_update(db, ctx, piece_id, body)


@router.get("/piece-updates/{update_id}/photo")
def get_piece_update_photo(update_id: UUID, ctx: OwnWork, db: DbSession) -> Response:
    """La foto de un avance (para verla en la ficha o en Mis tareas)."""
    return updates.update_photo(db, ctx, update_id)


@router.get("/pieces/open")
def list_open_pieces(ctx: View, db: DbSession) -> list[OpenPiece]:
    """Piezas sin montar de eventos aprobados o en producción (las propias primero): para elegir
    a qué pieza va una foto de avance."""
    return my_work.open_pieces(db, ctx)


@router.get("/pieces/{piece_id}/plans")
def list_piece_plans(piece_id: UUID, ctx: OwnWork, db: DbSession) -> list[PlanOut]:
    """Los planos de la pieza: por título, la versión vigente primero."""
    return plans.list_plans(db, ctx, piece_id)


@router.post("/pieces/{piece_id}/plans", status_code=status.HTTP_201_CREATED)
def add_piece_plan(piece_id: UUID, body: PlanIn, ctx: Manage, db: DbSession) -> PlanOut:
    """Subir un plano (PDF o imagen). Con un título que ya existe es la versión siguiente."""
    return plans.add_plan(db, ctx, piece_id, body)


@router.get("/piece-plans/{plan_id}/file")
def get_piece_plan_file(plan_id: UUID, ctx: OwnWork, db: DbSession) -> Response:
    """El archivo del plano. Lo ve quien ve el evento o tiene la pieza asignada."""
    return plans.plan_file(db, ctx, plan_id)


@router.get("/activity")
def get_activity(
    ctx: View, db: DbSession, before: datetime | None = None, event_id: UUID | None = None
) -> ActivityPage:
    """Lo que pasa en producción, lo más nuevo primero (de a 30; ``before`` trae los anteriores).
    Con ``event_id``, solo ese evento."""
    return activity.feed(db, ctx, before, event_id)


@router.get("/piece-updates/{update_id}/audio")
def get_piece_update_audio(update_id: UUID, ctx: OwnWork, db: DbSession) -> Response:
    """La nota de voz de un avance (para escucharla en la ficha o en Actividad)."""
    return updates.update_audio(db, ctx, update_id)


@router.get("/activity/unread")
def get_activity_unread(ctx: View, db: DbSession) -> UnreadOut:
    """La campanita: movimientos de otros desde la última vez que se abrió Actividad."""
    return activity.unread(db, ctx)


@router.post("/activity/seen")
def mark_activity_seen(body: ActivitySeenIn, ctx: View, db: DbSession) -> UnreadOut:
    """Abrir Actividad apaga la campanita (para quien la abre, no para los demás)."""
    return activity.mark_seen(db, ctx)


@router.get("/events/{event_id}/files")
def list_event_files(event_id: UUID, ctx: View, db: DbSession) -> EventFilesOut:
    """Archivos del evento: los subidos y los links, más los planos y las fotos de avance."""
    return files.list_files(db, ctx, event_id)


@router.post("/events/{event_id}/files", status_code=status.HTTP_201_CREATED)
def add_event_file(event_id: UUID, body: EventFileIn, ctx: View, db: DbSession) -> FileItem:
    """Subir un archivo (PDF o imagen) o pegar un link, con categoría y pieza opcional.
    Producción o comercial; el resto ve pero no sube."""
    return files.add_file(db, ctx, event_id, body)


@router.delete("/event-files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event_file(file_id: UUID, ctx: View, db: DbSession) -> None:
    files.delete_file(db, ctx, file_id)


@router.get("/event-files/{file_id}/file")
def open_event_file(file_id: UUID, ctx: View, db: DbSession) -> Response:
    return files.open_file(db, ctx, file_id)


@router.get("/files/search")
def search_files(q: str, ctx: View, db: DbSession) -> list[FileItem]:
    """Buscar archivos por título, pieza o evento, en todos los eventos (los 30 más nuevos)."""
    return files.search(db, ctx, q)


@router.post("/events/{event_id}/expected-files")
def add_expected_file(
    event_id: UUID, body: ExpectedFileIn, ctx: View, db: DbSession
) -> EventFilesOut:
    """Agregar a la lista de archivos que el evento tiene que tener (devuelve la pestaña)."""
    return files.add_expected(db, ctx, event_id, body)


@router.post("/events/{event_id}/expected-files/template")
def apply_expected_template(
    event_id: UUID, body: ExpectedTemplateIn, ctx: View, db: DbSession
) -> EventFilesOut:
    """Sumar la lista base según el tipo de evento (Stand, Activación BTL, Evento, Visual)."""
    return files.apply_template(db, ctx, event_id, body)


@router.delete("/expected-files/{expected_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expected_file(expected_id: UUID, ctx: View, db: DbSession) -> None:
    files.delete_expected(db, ctx, expected_id)


# --- Aprobación de diseños por link ------------------------------------------------------


@router.post("/event-files/{file_id}/approval", status_code=status.HTTP_201_CREATED)
def request_approval(file_id: UUID, ctx: View, db: DbSession) -> ApprovalLinkOut:
    """Arma el link para que el cliente apruebe el diseño (el anterior sin responder se anula)."""
    return approvals.request(db, ctx, file_id)


@public_router.get("/approvals/{token}", dependencies=[Public])
def public_approval(token: Token, db: DbSession, client: Client) -> PublicApproval:
    """Lo que ve el cliente: el título y el diseño, nada más del evento."""
    enforce(f"approval:ip:{client.ip}", limit=120, window_seconds=600)
    return approvals.public_view(db, token)


@public_router.get("/approvals/{token}/file", dependencies=[Public], response_class=Response)
def public_approval_file(token: Token, db: DbSession, client: Client) -> Response:
    enforce(f"approval:ip:{client.ip}", limit=120, window_seconds=600)
    return approvals.public_file(db, token)


@public_router.post("/approvals/{token}/decision", dependencies=[Public])
def public_approval_decision(
    token: Token, body: ApprovalDecisionIn, db: DbSession, client: Client
) -> PublicApproval:
    """ "Aprobado" o "Pido cambios" (con comentario). Queda quién, cuándo y desde dónde."""
    enforce(f"approval-decision:ip:{client.ip}", limit=20, window_seconds=600)
    return approvals.decide(db, token, body, client)


@router.get(
    "/events/{event_id}/download",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_event(event_id: UUID, ctx: View, db: DbSession) -> Response:
    """Todo el evento en un .zip ordenado en carpetas (los comprobantes, solo si ve costos)."""
    return bundle.download(db, ctx, event_id)


# --- Ficha del lugar ---------------------------------------------------------------------


@router.get("/events/{event_id}/venue-sheet")
def get_venue_sheet(event_id: UUID, ctx: View, db: DbSession) -> EventVenueOut:
    """La ficha del lugar del evento: accesos, horario de carga, medidas, reglas y contactos."""
    return venues.for_event(db, ctx, event_id)


@router.put("/events/{event_id}/venue-sheet")
def save_venue_sheet(event_id: UUID, body: VenueSheetIn, ctx: View, db: DbSession) -> EventVenueOut:
    """Guarda la ficha del lugar: queda para todos los eventos en ese mismo lugar."""
    return venues.save(db, ctx, event_id, body)
