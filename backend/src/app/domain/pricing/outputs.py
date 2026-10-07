from dataclasses import dataclass
from decimal import Decimal

from app.domain.pricing.types import MarkupSource, Warning_


@dataclass(frozen=True)
class LinePriced:
    key: str
    unit_cost_effective: Decimal
    cost_total: Decimal
    markup_applied: Decimal | None  # (P - C) / C; None si C = 0
    markup_source: MarkupSource
    markup_source_id: str | None
    sale_list_total: Decimal
    sale_total: Decimal  # P: lo que ve el cliente por esta línea (sin IVA)
    profit: Decimal
    margin: Decimal | None  # (P - C) / P; None si P = 0
    allocated_global_discount: Decimal


@dataclass(frozen=True)
class ChargeAmount:
    name: str
    rate: Decimal
    amount: Decimal


@dataclass(frozen=True)
class VersionPriced:
    lines: tuple[LinePriced, ...]
    cost_direct: Decimal
    sale_subtotal: Decimal
    global_discount: Decimal
    management_fee: Decimal
    sale_net: Decimal  # ítems − descuento + fee de gestión
    sale_charges: tuple[ChargeAmount, ...]
    sale_charges_total: Decimal
    cost_total: Decimal
    profit: Decimal
    markup: Decimal | None
    margin_gross: Decimal | None
    margin_net: Decimal | None
    iva: Decimal
    total: Decimal
    warnings: tuple[Warning_, ...]
    engine_version: str


@dataclass(frozen=True)
class Presentation:
    """Importes que ve el cliente en otra moneda (p. ej. USD), con las mismas invariantes."""

    currency: str
    fx_rate: Decimal  # unidades de moneda base por 1 unidad de ``currency``
    lines: dict[str, Decimal]
    subtotal: Decimal
    global_discount: Decimal
    management_fee: Decimal
    net: Decimal
    iva: Decimal
    total: Decimal
