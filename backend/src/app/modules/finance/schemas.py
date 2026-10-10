from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.documents import DocumentOut
from app.modules.events import EventStatus
from app.modules.finance.models import ExpenseCurrency

Money = Decimal


class ExpenseIn(BaseModel):
    """Un gasto real (O-04). Con la línea presupuestada alcanza: proveedor y categoría salen
    de ella si no se indican. Sin línea, hace falta la categoría (D-21)."""

    description: str = Field(min_length=1, max_length=200)
    amount: Money = Field(gt=Decimal(0), max_digits=16, decimal_places=2)
    currency: ExpenseCurrency = ExpenseCurrency.ARS
    amount_includes_iva: bool = True
    iva_rate: Decimal = Field(
        default=Decimal("0.21"), ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    fx_rate: Decimal | None = Field(default=None, gt=Decimal(0), max_digits=14, decimal_places=6)
    expense_date: date | None = None  # hoy (Argentina) si no se indica
    line_key: UUID | None = None
    supplier_id: UUID | None = None
    category_id: UUID | None = None
    receipt_document_id: UUID | None = None  # subido antes con POST /documents/receipts


class ExpenseUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Money | None = Field(default=None, gt=Decimal(0), max_digits=16, decimal_places=2)
    currency: ExpenseCurrency | None = None
    amount_includes_iva: bool | None = None
    iva_rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    fx_rate: Decimal | None = Field(default=None, gt=Decimal(0), max_digits=14, decimal_places=6)
    expense_date: date | None = None
    line_key: UUID | None = None
    supplier_id: UUID | None = None
    category_id: UUID | None = None
    receipt_document_id: UUID | None = None  # null: quitar el comprobante


class ExpenseOut(BaseModel):
    id: UUID
    event_id: UUID
    description: str
    amount: Money
    currency: ExpenseCurrency
    amount_includes_iva: bool
    iva_rate: Decimal
    fx_rate: Decimal
    amount_base: Money  # efectivo, en pesos (lo que se compara con lo presupuestado)
    expense_date: date
    line_key: UUID | None
    line_name: str | None
    supplier_id: UUID | None
    supplier_name: str | None
    category_id: UUID | None
    category_name: str | None
    receipt: DocumentOut | None
    created_by_name: str | None
    created_at: datetime


class LineOption(BaseModel):
    """Una línea de la versión aceptada, para vincular el gasto (con su proveedor sugerido)."""

    line_key: UUID
    name: str
    section: str
    supplier_id: UUID | None
    supplier_name: str | None
    category_id: UUID | None
    category_name: str | None
    budgeted: Money


class ComparisonRow(BaseModel):
    """Presupuestado vs real de una línea, o de lo no presupuestado de una categoría."""

    key: str
    label: str
    section: str | None
    budgeted: Money | None  # None: no presupuestado
    actual: Money
    delta: Money | None
    delta_rate: Decimal | None  # (real − presupuestado) / presupuestado


class ExpensesOut(BaseModel):
    event_id: UUID
    editable: bool
    receipts_enabled: bool  # hay dónde guardar archivos (D-17)
    has_baseline: bool
    items: list[ExpenseOut]
    lines: list[LineOption]
    comparison: list[ComparisonRow]  # por línea + no presupuestado
    by_category: list[ComparisonRow]
    by_supplier: list[ComparisonRow]
    budgeted_total: Money
    actual_total: Money
    delta_rate: Decimal | None


class ResultOut(BaseModel):
    sale_net: Money
    cost: Money
    sale_charges: Money
    profit: Money
    margin: Decimal | None


class ProfitabilityOut(BaseModel):
    """Rentabilidad del evento: estimada (versión aceptada) vs real (gastos cargados)."""

    event_id: UUID
    status: EventStatus
    final: bool  # cerrado: ya no cambia; si no, lo real es parcial
    estimated: ResultOut | None  # None: sin presupuesto aprobado
    actual: ResultOut | None
    cost_delta: Money | None
    cost_delta_rate: Decimal | None
    expenses_count: int
