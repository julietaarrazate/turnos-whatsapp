"""Traduce los vectores JSON (strings) a entradas del motor."""

from decimal import Decimal
from typing import Any

from app.domain.pricing import (
    ChargeMode,
    LineInput,
    LinePricingMode,
    MarkupRule,
    PricingContext,
    RuleMode,
    SaleCharge,
    TaxCondition,
    VersionInput,
    VersionPricingMode,
)

_DEC_FIELDS = {
    "quantity",
    "unit_cost",
    "cost_iva_rate",
    "iva_rate",
    "markup_manual",
    "target_margin",
    "target_price",
    "discount_rate",
}


def rule(data: dict[str, Any]) -> MarkupRule:
    return MarkupRule(
        value=Decimal(data["value"]),
        mode=RuleMode(data.get("mode", "MARKUP")),
        source_id=data.get("source_id"),
    )


def line(data: dict[str, Any]) -> LineInput:
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key in _DEC_FIELDS:
            kwargs[key] = Decimal(value)
        elif key == "charge_mode":
            kwargs[key] = ChargeMode(value)
        elif key == "pricing_mode":
            kwargs[key] = LinePricingMode(value)
        elif key == "product_rule":
            kwargs[key] = rule(value)
        elif key == "category_rules":
            kwargs[key] = tuple(rule(r) for r in value)
        else:
            kwargs[key] = value
    return LineInput(**kwargs)


def context(data: dict[str, Any]) -> PricingContext:
    return PricingContext(
        tax_condition=TaxCondition(data.get("tax_condition", "RI")),
        org_rule=MarkupRule(Decimal(data["org_markup"]), source_id="org"),
        client_rule=rule(data["client_rule"]) if "client_rule" in data else None,
        sale_charges=tuple(SaleCharge(n, Decimal(r)) for n, r in data.get("sale_charges", [])),
        rounding_increment=Decimal(data.get("rounding_increment", "0.01")),
        min_margin=Decimal(data["min_margin"]) if data.get("min_margin") else None,
    )


def version(data: dict[str, Any]) -> VersionInput:
    def dec(key: str) -> Decimal | None:
        return Decimal(data[key]) if data.get(key) is not None else None

    return VersionInput(
        lines=tuple(line(item) for item in data["lines"]),
        mode=VersionPricingMode(data.get("mode", "LINE")),
        markup_override=dec("markup_override"),
        target_margin=dec("target_margin"),
        target_price=dec("target_price"),
        target_includes_iva=data.get("target_includes_iva", False),
        global_discount_rate=dec("global_discount_rate") or Decimal(0),
    )
