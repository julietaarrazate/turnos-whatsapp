from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.pricing import MarkupSource, RuleMode
from app.modules.pricing.models import MarkupScope


class RoundingIncrement(StrEnum):
    """Incremento comercial al que se redondea cada línea (DOMAIN_MODEL §5.1)."""

    CENT = "0.01"
    ONE = "1"
    TEN = "10"
    HUNDRED = "100"
    THOUSAND = "1000"


# --- Configuración -------------------------------------------------------------------------


class PricingSettings(BaseModel):
    rounding_increment: RoundingIncrement = RoundingIncrement.CENT
    min_margin: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=7, decimal_places=6
    )
    margin_includes_sale_charges: bool = True
    price_staleness_days: int = Field(default=30, ge=1, le=365)


class PricingSettingsUpdate(BaseModel):
    rounding_increment: RoundingIncrement | None = None
    min_margin: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=7, decimal_places=6
    )
    margin_includes_sale_charges: bool | None = None
    price_staleness_days: int | None = Field(default=None, ge=1, le=365)


# --- Reglas de markup ----------------------------------------------------------------------


class MarkupRuleIn(BaseModel):
    """Crea o reemplaza la regla de ese alcance (hay una sola por alcance)."""

    scope: MarkupScope
    scope_id: UUID | None = None
    mode: RuleMode = RuleMode.MARKUP
    value: Decimal = Field(ge=Decimal(0), le=Decimal(100), max_digits=9, decimal_places=6)

    @model_validator(mode="after")
    def _check(self) -> "MarkupRuleIn":
        if (self.scope is MarkupScope.ORG) != (self.scope_id is None):
            raise ValueError("scope_id es obligatorio salvo para la regla general (ORG)")
        if self.mode is RuleMode.MARGIN and self.value >= 1:
            raise ValueError("Un margen tiene que ser menor a 100 %")
        return self


class MarkupRuleOut(BaseModel):
    id: UUID
    scope: MarkupScope
    scope_id: UUID | None
    scope_name: str | None  # nombre de la categoría, producto o cliente
    mode: RuleMode
    value: Decimal
    effective_markup: Decimal  # el margen convertido a markup: m = g / (1 − g)
    updated_at: datetime


class MarkupResolution(BaseModel):
    """Qué markup tomaría una línea nueva de ese producto para ese cliente, y por qué."""

    markup: Decimal
    margin: Decimal
    source: MarkupSource
    source_id: UUID | None
    source_name: str | None


# --- Cargos sobre la venta -----------------------------------------------------------------


class SaleChargeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rate: Decimal = Field(ge=Decimal(0), lt=Decimal(1), max_digits=7, decimal_places=6)
    is_active: bool = True
    applies_by_default: bool = True
    sort: int = Field(default=0, ge=0, le=10_000)


class SaleChargeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=7, decimal_places=6
    )
    is_active: bool | None = None
    applies_by_default: bool | None = None
    sort: int | None = Field(default=None, ge=0, le=10_000)


class SaleChargeOut(BaseModel):
    id: UUID
    name: str
    rate: Decimal
    is_active: bool
    applies_by_default: bool
    sort: int


# --- Tipo de cambio ------------------------------------------------------------------------


class FxCurrency(StrEnum):
    USD = "USD"


class FxRateIn(BaseModel):
    currency: FxCurrency = FxCurrency.USD
    rate: Decimal = Field(gt=Decimal(0), max_digits=18, decimal_places=6)
    rate_date: date | None = None  # por defecto, hoy (hora de Argentina)


class FxRateOut(BaseModel):
    id: UUID
    currency: FxCurrency
    rate: Decimal
    rate_date: date
    source: str
    days_old: int
    created_by_name: str | None
    created_at: datetime
