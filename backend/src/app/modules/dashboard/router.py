from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.dashboard import reports, service
from app.modules.dashboard.reports import ReportGroup
from app.modules.dashboard.schemas import ClientHistoryOut, DashboardOut, ReportOut

router = APIRouter(prefix="/api/v1", tags=["dashboard"])

View = Annotated[TenantContext, Depends(require(Permission.DASHBOARD_VIEW))]
OrgView = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
# La rentabilidad muestra ganancias y márgenes.
Margins = Annotated[TenantContext, Depends(require(Permission.MARGIN_VIEW))]
_CSV: dict[int | str, dict[str, Any]] = {200: {"content": {"text/csv": {}}, "description": "CSV"}}


@router.get("/dashboard")
def get_dashboard(
    ctx: View,
    db: DbSession,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> DashboardOut:
    """Enviado, aceptado, en negociación, margen y conversión; para hacer hoy; próximos eventos."""
    return service.dashboard(db, ctx, month)


From = Annotated[date, Query(alias="from")]
To = Annotated[date, Query(alias="to")]


@router.get("/reports/profitability")
def profitability_report(
    ctx: Margins,
    db: DbSession,
    date_from: From,
    date_to: To,
    group: ReportGroup = ReportGroup.EVENT,
) -> ReportOut:
    """A-02: rentabilidad estimada y real por evento, cliente o mes (eventos con fecha en el
    rango y presupuesto aceptado)."""
    return reports.profitability_report(db, ctx, date_from=date_from, date_to=date_to, group=group)


@router.get("/reports/profitability.csv", response_class=Response, responses=_CSV)
def profitability_csv(
    ctx: Margins,
    db: DbSession,
    date_from: From,
    date_to: To,
    group: ReportGroup = ReportGroup.EVENT,
) -> Response:
    """El mismo reporte en CSV (separador ";" y coma decimal, para Excel en español)."""
    report = reports.profitability_report(
        db, ctx, date_from=date_from, date_to=date_to, group=group
    )
    filename = f"rentabilidad-{date_from}-{date_to}.csv"
    return Response(
        content=reports.report_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/clients/{client_id}/history")
def client_history(client_id: UUID, ctx: OrgView, db: DbSession) -> ClientHistoryOut:
    """Historial comercial del cliente: presupuestos, aceptados, perdidos, facturado y margen."""
    return reports.client_history(db, ctx, client_id, margins=ctx.can(Permission.MARGIN_VIEW))
