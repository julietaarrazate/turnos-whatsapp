"""Entradas inmutables del motor. El service las arma (con las queries) y el motor solo calcula."""

from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.pricing.types import (
    CENT,
    ZERO,
    ChargeMode,
    LinePricingMode,
    RuleMode,
    TaxCondition,
    VersionPricingMode,
)

IVA_GENERAL = Decimal("0.21")


@dataclass(frozen=True)
class MarkupRule:
    """Una regla de markup o margen (organización, categoría, producto o cliente)."""

    value: Decimal
    mode: RuleMode = RuleMode.MARKUP
    source_id: str | None = None


@dataclass(frozen=True)
class SaleCharge:
    """Cargo proporcional a la venta neta (IIBB, impuesto al cheque, comisiones)."""

    name: str
    rate: Decimal


@dataclass(frozen=True)
class PricingContext:
    tax_condition: TaxCondition
    org_rule: MarkupRule
    client_rule: MarkupRule | None = None
    sale_charges: tuple[SaleCharge, ...] = ()
    rounding_increment: Decimal = CENT
    margin_includes_sale_charges: bool = True
    default_iva_rate: Decimal = IVA_GENERAL
    min_margin: Decimal | None = None  # aviso (no bloquea en el MVP)


@dataclass(frozen=True)
class LineInput:
    key: str
    quantity: Decimal
    unit_cost: Decimal  # tal como lo cotizó el proveedor
    days: int = 1
    charge_mode: ChargeMode = ChargeMode.FIXED
    cost_includes_iva: bool = False
    cost_iva_rate: Decimal = IVA_GENERAL  # 0 si el proveedor no discrimina IVA
    iva_rate: Decimal = IVA_GENERAL  # alícuota de la venta
    pricing_mode: LinePricingMode = LinePricingMode.MARKUP
    markup_manual: Decimal | None = None
    target_margin: Decimal | None = None
    target_price: Decimal | None = None  # importe total de la línea, sin IVA
    discount_rate: Decimal = ZERO
    locked: bool = False
    product_rule: MarkupRule | None = None
    # De la categoría más específica a la más general (categoría, categoría padre).
    category_rules: tuple[MarkupRule, ...] = ()


@dataclass(frozen=True)
class VersionInput:
    lines: tuple[LineInput, ...]
    mode: VersionPricingMode = VersionPricingMode.LINE
    markup_override: Decimal | None = None
    target_margin: Decimal | None = None
    target_price: Decimal | None = None
    target_includes_iva: bool = False
    global_discount_rate: Decimal = ZERO
    meta: dict[str, str] = field(default_factory=dict)
