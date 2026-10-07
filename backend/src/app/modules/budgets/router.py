import hashlib
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.core.db import DbSession
from app.core.idempotency import run_idempotent
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.budgets import service
from app.modules.budgets.schemas import (
    BudgetCreate,
    BudgetImportIn,
    BudgetOut,
    BudgetPage,
    CompareOut,
    CostsPreview,
    DuplicateIn,
    DuplicateOut,
    FreezeIn,
    ImportPreviewOut,
    LineIn,
    LineUpdate,
    RefreshCostsIn,
    RulesPreview,
    SectionIn,
    SectionUpdate,
    SheetImportIn,
    VersionUpdate,
)

router = APIRouter(prefix="/api/v1/budgets", tags=["budgets"])

# Ver un presupuesto: cualquiera de la organización; costos y márgenes se ocultan según permisos.
View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Edit = Annotated[TenantContext, Depends(require(Permission.BUDGET_EDIT))]
# Lock optimista: el lock_version que vio el cliente (ARCHITECTURE §4.5).
CostView = Annotated[TenantContext, Depends(require(Permission.COST_VIEW))]
MarginView = Annotated[TenantContext, Depends(require(Permission.MARGIN_VIEW))]
IfMatch = Annotated[str, Header(alias="If-Match", max_length=40)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)]


@router.get("")
def list_budgets(
    ctx: View,
    db: DbSession,
    *,
    q: Annotated[str | None, Query(max_length=100)] = None,
    event_id: UUID | None = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> BudgetPage:
    return service.list_budgets(db, ctx, q=q, event_id=event_id, cursor=cursor, limit=limit)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_budget(
    body: BudgetCreate, ctx: Edit, db: DbSession, idempotency_key: IdempotencyKey = None
) -> BudgetOut:
    """Nuevo presupuesto (y, si hace falta, el evento y el cliente) con un borrador vacío."""
    return run_idempotent(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user_id,
        key=idempotency_key,
        scope="budget.create",
        payload=body.model_dump(mode="json"),
        model=BudgetOut,
        run=lambda: service.create_budget(db, ctx, body),
    )


@router.post("/import/preview")
def preview_import(body: SheetImportIn, ctx: Edit) -> ImportPreviewOut:
    """Leer la planilla de presupuesto de la productora (.xlsx) sin guardar nada."""
    return service.preview_import(ctx, body)


@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_budget(
    body: BudgetImportIn, ctx: Edit, db: DbSession, idempotency_key: IdempotencyKey = None
) -> BudgetOut:
    """Nuevo presupuesto con los rubros, líneas, costos y fee de una hoja de la planilla."""
    payload = body.model_dump(mode="json", exclude={"file_base64"})
    payload["file_sha256"] = hashlib.sha256(body.file_base64.encode()).hexdigest()
    return run_idempotent(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user_id,
        key=idempotency_key,
        scope="budget.import",
        payload=payload,
        model=BudgetOut,
        run=lambda: service.import_budget(db, ctx, body),
    )


@router.get("/{budget_id}")
def get_budget(budget_id: UUID, ctx: View, db: DbSession) -> BudgetOut:
    """El presupuesto con su borrador (o la última versión congelada)."""
    return service.get_budget(db, ctx, budget_id)


@router.get("/{budget_id}/versions/{version_no}")
def get_version(budget_id: UUID, version_no: int, ctx: View, db: DbSession) -> BudgetOut:
    return service.get_version(db, ctx, budget_id, version_no)


_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_XLSX_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {_XLSX: {}}, "description": "Planilla de la versión"}
}


@router.get(
    "/{budget_id}/versions/{version_no}/export.xlsx",
    response_class=Response,
    responses=_XLSX_RESPONSE,
)
def export_version(budget_id: UUID, version_no: int, ctx: View, db: DbSession) -> Response:
    """Excel de la versión: costos y márgenes solo si el rol los puede ver."""
    content, filename = service.export_version(db, ctx, budget_id, version_no)
    return Response(
        content=content,
        media_type=_XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{budget_id}/compare")
def compare_versions(
    budget_id: UUID,
    ctx: View,
    db: DbSession,
    *,
    before: Annotated[int, Query(alias="from", ge=1)],
    after: Annotated[int, Query(alias="to", ge=1)],
) -> CompareOut:
    """Qué cambió entre dos versiones: ítems agregados, quitados y modificados (por line_key)."""
    return service.compare_versions(db, ctx, budget_id, before, after)


@router.post("/{budget_id}/versions", status_code=status.HTTP_201_CREATED)
def new_version(budget_id: UUID, ctx: Edit, db: DbSession) -> BudgetOut:
    """Nueva versión: un borrador que clona la última (sin actualizar costos ni reglas)."""
    return service.new_version(db, ctx, budget_id)


@router.patch("/{budget_id}/draft")
def update_version(
    budget_id: UUID, body: VersionUpdate, if_match: IfMatch, ctx: Edit, db: DbSession
) -> BudgetOut:
    return service.update_version(db, ctx, budget_id, service.parse_if_match(if_match), body)


@router.delete("/{budget_id}/draft")
def discard_draft(budget_id: UUID, if_match: IfMatch, ctx: Edit, db: DbSession) -> BudgetOut:
    return service.discard_draft(db, ctx, budget_id, service.parse_if_match(if_match))


@router.post("/{budget_id}/draft/freeze")
def freeze(
    budget_id: UUID, body: FreezeIn, if_match: IfMatch, ctx: Edit, db: DbSession
) -> BudgetOut:
    """ "Guardar versión": el borrador queda congelado y ya no cambia."""
    return service.freeze(db, ctx, budget_id, service.parse_if_match(if_match), body)


@router.post("/{budget_id}/draft/sections", status_code=status.HTTP_201_CREATED)
def add_section(
    budget_id: UUID, body: SectionIn, if_match: IfMatch, ctx: Edit, db: DbSession
) -> BudgetOut:
    return service.add_section(db, ctx, budget_id, service.parse_if_match(if_match), body)


@router.patch("/{budget_id}/draft/sections/{section_id}")
def update_section(
    budget_id: UUID,
    section_id: UUID,
    *,
    body: SectionUpdate,
    if_match: IfMatch,
    ctx: Edit,
    db: DbSession,
) -> BudgetOut:
    return service.update_section(
        db, ctx, budget_id, section_id, if_match=service.parse_if_match(if_match), body=body
    )


@router.delete("/{budget_id}/draft/sections/{section_id}")
def delete_section(
    budget_id: UUID, section_id: UUID, if_match: IfMatch, ctx: Edit, db: DbSession
) -> BudgetOut:
    return service.delete_section(db, ctx, budget_id, section_id, service.parse_if_match(if_match))


@router.post("/{budget_id}/draft/lines", status_code=status.HTTP_201_CREATED)
def add_line(
    budget_id: UUID,
    *,
    body: LineIn,
    if_match: IfMatch,
    ctx: Edit,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> BudgetOut:
    """Agrega una línea del catálogo (con su costo vigente y el markup de las reglas) o libre."""
    lock = service.parse_if_match(if_match)
    return run_idempotent(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user_id,
        key=idempotency_key,
        scope=f"budget.{budget_id}.line",
        payload=body.model_dump(mode="json"),
        model=BudgetOut,
        run=lambda: service.add_line(db, ctx, budget_id, lock, body),
    )


@router.patch("/{budget_id}/draft/lines/{line_id}")
def update_line(
    budget_id: UUID,
    line_id: UUID,
    *,
    body: LineUpdate,
    if_match: IfMatch,
    ctx: Edit,
    db: DbSession,
) -> BudgetOut:
    """Cambia inputs de la línea (cantidad, días, costo, modo, markup, descuento, orden)."""
    return service.update_line(
        db, ctx, budget_id, line_id, if_match=service.parse_if_match(if_match), body=body
    )


@router.delete("/{budget_id}/draft/lines/{line_id}")
def delete_line(
    budget_id: UUID, line_id: UUID, if_match: IfMatch, ctx: Edit, db: DbSession
) -> BudgetOut:
    return service.delete_line(db, ctx, budget_id, line_id, service.parse_if_match(if_match))


@router.get("/{budget_id}/draft/refresh-costs")
def preview_refresh_costs(budget_id: UUID, ctx: CostView, db: DbSession) -> CostsPreview:
    """Qué líneas tienen un costo más nuevo en el catálogo y cómo cambiarían los totales."""
    return service.preview_refresh_costs(db, ctx, budget_id)


@router.post("/{budget_id}/draft/refresh-costs")
def refresh_costs(
    budget_id: UUID, body: RefreshCostsIn, if_match: IfMatch, ctx: Edit, db: DbSession
) -> BudgetOut:
    """Toma el costo vigente del catálogo para las líneas indicadas (o todas)."""
    return service.refresh_costs(db, ctx, budget_id, service.parse_if_match(if_match), body)


@router.get("/{budget_id}/draft/reapply-rules")
def preview_reapply_rules(budget_id: UUID, ctx: MarginView, db: DbSession) -> RulesPreview:
    """Qué markups y cargos cambiarían con las reglas de hoy, y el efecto en los totales."""
    return service.preview_reapply_rules(db, ctx, budget_id)


@router.post("/{budget_id}/draft/reapply-rules")
def reapply_rules(budget_id: UUID, if_match: IfMatch, ctx: Edit, db: DbSession) -> BudgetOut:
    return service.reapply_rules(db, ctx, budget_id, service.parse_if_match(if_match))


@router.post("/{budget_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate(
    budget_id: UUID,
    body: DuplicateIn,
    ctx: Edit,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> DuplicateOut:
    """Duplicar para otro evento: copia la última versión con los costos y reglas de hoy."""
    return run_idempotent(
        db,
        organization_id=ctx.organization_id,
        user_id=ctx.user_id,
        key=idempotency_key,
        scope=f"budget.{budget_id}.duplicate",
        payload=body.model_dump(mode="json"),
        model=DuplicateOut,
        run=lambda: service.duplicate(db, ctx, budget_id, body),
    )
