from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.pricing import ChargeMode, LinePricingMode, MarkupSource, VersionPricingMode
from app.modules.budgets.models import BudgetCurrency, VersionStatus
from app.modules.events import EventIn, EventStatus

Fraction = Decimal  # fracción como string en JSON: "0.350000" = 35 %


# --- Entrada -------------------------------------------------------------------------------


class BudgetCreate(BaseModel):
    """B-01: presupuesto para un evento existente o creando el evento (y el cliente) en el
    mismo paso."""

    event_id: UUID | None = None
    event: EventIn | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    currency: BudgetCurrency = BudgetCurrency.ARS

    @model_validator(mode="after")
    def _check(self) -> "BudgetCreate":
        if (self.event_id is None) == (self.event is None):
            raise ValueError("Indicá un evento existente o los datos de uno nuevo")
        return self


class VersionUpdate(BaseModel):
    """Modo de pricing de la versión (§5.5), descuento global y moneda."""

    pricing_mode: VersionPricingMode | None = None
    markup_override: Fraction | None = Field(
        default=None, max_digits=14, decimal_places=6, gt=Decimal(-1), le=Decimal(100)
    )
    target_margin: Fraction | None = Field(
        default=None, max_digits=14, decimal_places=6, ge=Decimal(0), lt=Decimal(1)
    )
    target_price: Decimal | None = Field(
        default=None, gt=Decimal(0), max_digits=18, decimal_places=2
    )
    target_includes_iva: bool | None = None
    global_discount_rate: Fraction | None = Field(
        default=None, max_digits=14, decimal_places=6, ge=Decimal(0), lt=Decimal(1)
    )
    currency: BudgetCurrency | None = None
    refresh_fx: bool = False  # tomar el último tipo de cambio cargado


class SectionIn(BaseModel):
    title_client: str = Field(min_length=1, max_length=200)


class SectionUpdate(BaseModel):
    title_client: str | None = Field(default=None, min_length=1, max_length=200)
    position: int | None = Field(default=None, ge=0, le=1000)


class LineIn(BaseModel):
    """Del catálogo (`product_id`, opcionalmente `offer_id`) o libre (`name` y costo)."""

    section_id: UUID
    product_id: UUID | None = None
    offer_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: UUID | None = None
    unit_code: str | None = Field(default=None, min_length=1, max_length=16)
    charge_mode: ChargeMode | None = None
    unit_cost_amount: Decimal | None = Field(
        default=None, ge=Decimal(0), max_digits=18, decimal_places=6
    )
    unit_cost_includes_iva: bool | None = None
    unit_cost_iva_rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    iva_rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    quantity: Decimal = Field(default=Decimal(1), gt=Decimal(0), max_digits=14, decimal_places=4)
    days: int | None = Field(default=None, ge=1, le=365)
    position: int | None = Field(default=None, ge=0, le=10_000)

    @model_validator(mode="after")
    def _check(self) -> "LineIn":
        if self.product_id is None and self.name is None:
            raise ValueError("Elegí un producto del catálogo o escribí el nombre de la línea")
        if self.product_id is None and self.offer_id is not None:
            raise ValueError("offer_id requiere product_id")
        return self


class LineUpdate(BaseModel):
    """Solo inputs: los importes los calcula el motor (I8)."""

    section_id: UUID | None = None
    position: int | None = Field(default=None, ge=0, le=10_000)
    name_internal: str | None = Field(default=None, min_length=1, max_length=200)
    description_client: str | None = Field(default=None, max_length=5000)
    notes_internal: str | None = Field(default=None, max_length=5000)
    show_on_proposal: bool | None = None
    quantity: Decimal | None = Field(default=None, gt=Decimal(0), max_digits=14, decimal_places=4)
    days: int | None = Field(default=None, ge=1, le=365)
    charge_mode: ChargeMode | None = None
    iva_rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    offer_id: UUID | None = None  # cambiar de proveedor: toma su costo vigente
    unit_cost_amount: Decimal | None = Field(
        default=None, ge=Decimal(0), max_digits=18, decimal_places=6
    )
    unit_cost_includes_iva: bool | None = None
    unit_cost_iva_rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    pricing_mode: LinePricingMode | None = None
    markup_manual: Fraction | None = Field(
        default=None, max_digits=14, decimal_places=6, gt=Decimal(-1), le=Decimal(100)
    )
    target_margin: Fraction | None = Field(
        default=None, max_digits=14, decimal_places=6, ge=Decimal(0), lt=Decimal(1)
    )
    target_price: Decimal | None = Field(
        default=None, ge=Decimal(0), max_digits=18, decimal_places=2
    )
    discount_rate: Fraction | None = Field(
        default=None, max_digits=14, decimal_places=6, ge=Decimal(0), lt=Decimal(1)
    )
    is_locked: bool | None = None


class FreezeIn(BaseModel):
    change_note: str | None = Field(default=None, max_length=2000)


# --- Salida --------------------------------------------------------------------------------


class LineCost(BaseModel):
    """Solo con `cost.view`."""

    unit_cost_amount: Decimal
    unit_cost_includes_iva: bool
    unit_cost_iva_rate: Decimal
    unit_cost_effective: Decimal
    cost_total: Decimal
    cost_as_of: date | None
    cost_days_old: int | None
    cost_stale: bool
    supplier_product_id: UUID | None


class LineMargin(BaseModel):
    """Solo con `margin.view`."""

    markup_manual: Decimal | None
    target_margin: Decimal | None
    rule_markup: Decimal
    rule_source: MarkupSource
    markup_applied: Decimal | None
    markup_source: MarkupSource | None
    profit: Decimal
    margin: Decimal | None


class LineOut(BaseModel):
    id: UUID
    line_key: UUID
    section_id: UUID
    sort: int
    product_id: UUID | None
    category_id: UUID | None
    category_name: str | None
    supplier_id: UUID | None
    supplier_name: str | None
    name_internal: str
    description_client: str | None
    notes_internal: str | None
    show_on_proposal: bool
    unit_code: str
    charge_mode: ChargeMode
    iva_rate: Decimal
    quantity: Decimal
    days: int
    pricing_mode: LinePricingMode
    target_price: Decimal | None
    discount_rate: Decimal
    is_locked: bool
    sale_list_total: Decimal
    sale_total: Decimal
    allocated_global_discount: Decimal
    cost: LineCost | None
    margin: LineMargin | None


class SectionOut(BaseModel):
    id: UUID
    section_key: UUID
    title_client: str
    sort: int
    sale_total: Decimal
    lines: list[LineOut]


class ChargeOut(BaseModel):
    name: str
    rate: Decimal
    amount: Decimal


class VersionCosts(BaseModel):
    cost_direct: Decimal


class VersionMargins(BaseModel):
    markup_override: Decimal | None
    target_margin: Decimal | None
    sale_charges: Decimal
    sale_charges_detail: list[ChargeOut]
    profit: Decimal
    markup: Decimal | None
    margin_gross: Decimal | None
    margin_net: Decimal | None
    min_margin: Decimal | None


class FxOut(BaseModel):
    currency: str
    rate: Decimal
    rate_date: date


class PresentationOut(BaseModel):
    currency: str
    fx_rate: Decimal
    subtotal: Decimal
    global_discount: Decimal
    net: Decimal
    iva: Decimal
    total: Decimal
    lines: dict[str, Decimal]  # line_id → importe en la moneda de presentación


class VersionOut(BaseModel):
    id: UUID
    version_no: int
    status: VersionStatus
    lock_version: int
    pricing_mode: VersionPricingMode
    target_price: Decimal | None
    target_includes_iva: bool
    global_discount_rate: Decimal
    sale_subtotal: Decimal
    global_discount: Decimal
    sale_net: Decimal
    iva: Decimal
    total: Decimal
    rounding_increment: Decimal
    fx: FxOut | None
    presentation: PresentationOut | None
    costs: VersionCosts | None
    margins: VersionMargins | None
    warnings: list[str]
    sections: list[SectionOut]
    change_note: str | None
    frozen_at: datetime | None
    updated_at: datetime


class VersionSummary(BaseModel):
    id: UUID
    version_no: int
    status: VersionStatus
    sale_net: Decimal
    total: Decimal
    change_note: str | None
    frozen_at: datetime | None
    updated_at: datetime


class BudgetEvent(BaseModel):
    id: UUID
    number: int
    name: str
    client_id: UUID
    client_name: str
    start_date: date | None
    event_days: int
    status: EventStatus


class BudgetOut(BaseModel):
    id: UUID
    number: int
    title: str
    currency: BudgetCurrency
    event: BudgetEvent
    version: VersionOut  # el borrador si hay; si no, la última versión congelada
    versions: list[VersionSummary]


class BudgetSummary(BaseModel):
    id: UUID
    number: int
    title: str
    currency: BudgetCurrency
    event_id: UUID
    event_name: str
    event_status: EventStatus
    client_name: str
    version_no: int
    version_status: VersionStatus
    sale_net: Decimal
    updated_at: datetime
    approved_version_no: int | None  # la versión que es baseline del evento, si es de este


class BudgetPage(BaseModel):
    items: list[BudgetSummary]
    next_cursor: str | None


# --- Actualizar costos, re-aplicar reglas, duplicar (B-07, B-08) ---------------------------


class CostChange(BaseModel):
    line_id: UUID
    name: str
    supplier_name: str | None
    old_unit_cost: Decimal
    new_unit_cost: Decimal
    old_as_of: date | None
    new_as_of: date
    amount_changed: bool  # False: misma cifra con fecha más nueva


class RuleChange(BaseModel):
    line_id: UUID
    name: str
    old_markup: Decimal
    new_markup: Decimal
    old_source: MarkupSource
    new_source: MarkupSource
    has_manual_markup: bool  # la línea tiene markup manual: el cambio no afecta su precio


class ChargeRate(BaseModel):
    name: str
    rate: Decimal


class TotalsDelta(BaseModel):
    sale_net_before: Decimal
    sale_net_after: Decimal
    profit_before: Decimal | None  # con margin.view
    profit_after: Decimal | None
    margin_net_before: Decimal | None
    margin_net_after: Decimal | None


class CostsPreview(BaseModel):
    changes: list[CostChange]
    totals: TotalsDelta


class RulesPreview(BaseModel):
    changes: list[RuleChange]
    charges_before: list[ChargeRate]
    charges_after: list[ChargeRate]
    totals: TotalsDelta


class RefreshCostsIn(BaseModel):
    line_ids: list[UUID] | None = Field(default=None, max_length=1000)  # None = todas


class DuplicateIn(BaseModel):
    """Copia la última versión a otro evento (existente o nuevo) con costos y reglas actuales."""

    event_id: UUID | None = None
    event: EventIn | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> "DuplicateIn":
        if (self.event_id is None) == (self.event is None):
            raise ValueError("Indicá un evento existente o los datos de uno nuevo")
        return self


class DuplicateOut(BaseModel):
    budget: BudgetOut
    costs_changed: int
    rules_changed: int


# --- Comparar versiones (DOMAIN_MODEL §8) ---------------------------------------------------


class DiffKind(StrEnum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"


class FieldChange(BaseModel):
    field: str
    before: str | None
    after: str | None


class LineDiff(BaseModel):
    line_key: UUID
    name: str
    kind: DiffKind
    section_before: str | None
    section_after: str | None
    sale_before: Decimal | None
    sale_after: Decimal | None
    changes: list[FieldChange]


class CompareOut(BaseModel):
    version_before: int
    version_after: int
    added: int
    removed: int
    modified: int
    reordered: int  # solo cambió el orden (se muestra aparte, sutil)
    lines: list[LineDiff]
    sale_net_before: Decimal
    sale_net_after: Decimal
    total_before: Decimal
    total_after: Decimal
    cost_before: Decimal | None  # con cost.view
    cost_after: Decimal | None
    profit_before: Decimal | None  # con margin.view
    profit_after: Decimal | None
    margin_net_before: Decimal | None
    margin_net_after: Decimal | None
    margin_delta_points: Decimal | None  # en puntos porcentuales
