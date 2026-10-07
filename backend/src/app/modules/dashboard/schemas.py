from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.modules.events import EventStatus


class AmountOut(BaseModel):
    count: int
    amount: Decimal


class ConversionOut(BaseModel):
    """Decisiones de los últimos 90 días: aceptadas / (aceptadas + rechazadas + vencidas)."""

    won: AmountOut
    lost: AmountOut
    by_count: Decimal | None
    by_amount: Decimal | None


class TodoOut(BaseModel):
    no_response: int  # enviadas hace más de N días sin decisión
    viewed_no_answer: int  # vistas hace más de 48 h, sin respuesta
    expiring: int  # vencen en menos de 48 h
    stale_costs: int  # líneas de borradores con costos desactualizados
    follow_up_days: int


class UpcomingEvent(BaseModel):
    id: UUID
    number: int
    name: str
    client_name: str
    start_date: date
    status: EventStatus
    margin: Decimal | None  # de la versión aceptada; None sin permiso o sin versión


class DashboardOut(BaseModel):
    month: str  # YYYY-MM
    own_only: bool  # QUOTER: solo sus presupuestos
    sent: AmountOut
    accepted: AmountOut
    in_negotiation: AmountOut
    avg_margin: Decimal | None  # ponderado por venta; None sin permiso o sin aceptados
    conversion: ConversionOut
    todo: TodoOut
    upcoming: list[UpcomingEvent]


class ReportRow(BaseModel):
    key: str
    label: str
    events: int
    sale_net: Decimal
    estimated_cost: Decimal
    estimated_profit: Decimal
    estimated_margin: Decimal | None
    events_with_costs: int  # la ganancia real solo cuenta eventos con gastos cargados
    actual_cost: Decimal | None
    actual_profit: Decimal | None
    actual_margin: Decimal | None
    cost_delta_rate: Decimal | None
    partial: bool  # algún evento del grupo todavía no está cerrado


class ReportOut(BaseModel):
    date_from: date
    date_to: date
    group: str
    rows: list[ReportRow]
    total: ReportRow
    truncated: bool


class ClientHistoryOut(BaseModel):
    """Historial comercial calculado del cliente (PRODUCT_SPEC §4.2)."""

    client_id: UUID
    budgets: int
    events: int
    accepted: int  # eventos con presupuesto aceptado
    lost: int
    conversion: Decimal | None
    billed: Decimal  # aceptado, sin IVA
    estimated_margin: Decimal | None  # None sin permiso de márgenes
    actual_margin: Decimal | None  # de los eventos con gastos cargados
    preferential_markup: Decimal | None  # regla de markup del cliente
    preferential_mode: str | None  # MARKUP o MARGIN
