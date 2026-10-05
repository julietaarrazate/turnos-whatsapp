"""Motor de pricing puro (DOMAIN_MODEL §5). Sin FastAPI, sin SQLAlchemy, sin I/O."""

from app.domain.pricing.engine import (
    ENGINE_VERSION,
    effective_unit_cost,
    present_in_currency,
    price_line,
    price_version,
    resolve_markup,
)
from app.domain.pricing.inputs import (
    LineInput,
    MarkupRule,
    PricingContext,
    ResolvedMarkup,
    SaleCharge,
    VersionInput,
)
from app.domain.pricing.outputs import ChargeAmount, LinePriced, Presentation, VersionPriced
from app.domain.pricing.rounding import allocate
from app.domain.pricing.types import (
    ChargeMode,
    LinePricingMode,
    MarkupSource,
    PricingError,
    RuleMode,
    TaxCondition,
    VersionPricingMode,
    Warning_,
)

__all__ = [
    "ENGINE_VERSION",
    "ChargeAmount",
    "ChargeMode",
    "LineInput",
    "LinePriced",
    "LinePricingMode",
    "MarkupRule",
    "MarkupSource",
    "Presentation",
    "PricingContext",
    "PricingError",
    "ResolvedMarkup",
    "RuleMode",
    "SaleCharge",
    "TaxCondition",
    "VersionInput",
    "VersionPriced",
    "VersionPricingMode",
    "Warning_",
    "allocate",
    "effective_unit_cost",
    "present_in_currency",
    "price_line",
    "price_version",
    "resolve_markup",
]
