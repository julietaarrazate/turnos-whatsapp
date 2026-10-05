"""Tipos y enums del motor. Todo es Decimal: nunca float."""

from decimal import Decimal
from enum import StrEnum

ZERO = Decimal(0)
ONE = Decimal(1)
CENT = Decimal("0.01")


class PricingError(ValueError):
    """Entrada inválida para el motor. ``code`` es estable (la API lo expone tal cual)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class TaxCondition(StrEnum):
    RI = "RI"
    MONOTRIBUTO = "MONOTRIBUTO"
    EXENTO = "EXENTO"


class ChargeMode(StrEnum):
    FIXED = "FIXED"
    PER_DAY = "PER_DAY"


class LinePricingMode(StrEnum):
    MARKUP = "MARKUP"
    MARGIN = "MARGIN"
    PRICE = "PRICE"


class VersionPricingMode(StrEnum):
    LINE = "LINE"  # cada línea con su modo y la cadena de markup
    MARKUP = "MARKUP"  # markup de la versión entra en la cadena (paso 2)
    MARGIN = "MARGIN"  # margen objetivo para todas las líneas no bloqueadas
    PRICE = "PRICE"  # precio objetivo repartido entre las líneas no bloqueadas


class RuleMode(StrEnum):
    MARKUP = "MARKUP"
    MARGIN = "MARGIN"


class MarkupSource(StrEnum):
    LINE = "LINE"
    VERSION = "VERSION"
    CLIENT = "CLIENT"
    PRODUCT = "PRODUCT"
    CATEGORY = "CATEGORY"
    ORG = "ORG"
    TARGET_MARGIN = "TARGET_MARGIN"
    TARGET_PRICE = "TARGET_PRICE"


class Warning_(StrEnum):  # noqa: N801 — evita chocar con el builtin Warning
    BELOW_COST = "below_cost"
    BELOW_MIN_MARGIN = "below_min_margin"
    TARGET_ROUNDED = "target_rounded"
