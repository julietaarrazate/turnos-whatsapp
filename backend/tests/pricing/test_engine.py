"""Ramas y reglas del motor que no cubren los vectores."""

from decimal import Decimal

import pytest

from app.domain.pricing import (
    ENGINE_VERSION,
    LineInput,
    LinePricingMode,
    MarkupRule,
    MarkupSource,
    PricingContext,
    PricingError,
    ResolvedMarkup,
    RuleMode,
    TaxCondition,
    VersionInput,
    VersionPricingMode,
    Warning_,
    effective_unit_cost,
    present_in_currency,
    price_version,
    resolve_markup,
)

D = Decimal
ORG = MarkupRule(D("0.30"), source_id="org")


def ctx(**kwargs: object) -> PricingContext:
    return PricingContext(tax_condition=TaxCondition.RI, org_rule=ORG, **kwargs)  # type: ignore[arg-type]


def one(**kwargs: object) -> LineInput:
    defaults: dict[str, object] = {"key": "a", "quantity": D(1), "unit_cost": D(1000)}
    return LineInput(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_markup_chain_precedence() -> None:
    client = MarkupRule(D("0.20"), source_id="cliente")
    product = MarkupRule(D("0.50"), source_id="producto")
    category = MarkupRule(D("0.35"), source_id="grafica")
    parent = MarkupRule(D("0.10"), source_id="padre")
    line = one(product_rule=product, category_rules=(category, parent))
    assert resolve_markup(line, None, ctx(client_rule=client))[1:] == (
        MarkupSource.CLIENT,
        "cliente",
    )
    assert resolve_markup(line, None, ctx())[1:] == (MarkupSource.PRODUCT, "producto")
    assert resolve_markup(one(category_rules=(category, parent)), None, ctx())[2] == "grafica"
    assert resolve_markup(one(category_rules=(parent,)), None, ctx())[2] == "padre"
    assert resolve_markup(one(), None, ctx())[1:] == (MarkupSource.ORG, "org")
    assert resolve_markup(line, D("0.15"), ctx(client_rule=client))[:2] == (
        D("0.15"),
        MarkupSource.VERSION,
    )
    assert resolve_markup(one(markup_manual=D("0.05")), D("0.15"), ctx())[1] is MarkupSource.LINE


def test_resolved_markup_replaces_rules_but_not_line_or_version() -> None:
    """§5.3: el markup resuelto al insertar queda en la línea; una regla nueva no lo cambia."""
    frozen = ResolvedMarkup(D("0.40"), MarkupSource.CATEGORY, "grafica")
    newer_client = ctx(client_rule=MarkupRule(D("0.10"), source_id="cliente"))
    line = one(resolved=frozen, product_rule=MarkupRule(D("0.90"), source_id="p"))
    assert resolve_markup(line, None, newer_client) == (D("0.40"), MarkupSource.CATEGORY, "grafica")
    assert resolve_markup(line, D("0.15"), newer_client) == (D("0.15"), MarkupSource.VERSION, None)
    manual = one(resolved=frozen, markup_manual=D("0.05"))
    assert resolve_markup(manual, D("0.15"), newer_client) == (D("0.05"), MarkupSource.LINE, None)


def test_margin_rules_are_converted_to_markup() -> None:
    rule = MarkupRule(D("0.25"), mode=RuleMode.MARGIN)
    markup, _, _ = resolve_markup(one(product_rule=rule), None, ctx())
    assert markup == D("0.25") / D("0.75")
    with pytest.raises(PricingError) as excinfo:
        resolve_markup(one(product_rule=MarkupRule(D(1), mode=RuleMode.MARGIN)), None, ctx())
    assert excinfo.value.code == "margin_out_of_range"


def test_version_markup_mode_respects_manual_lines() -> None:
    version = VersionInput(
        lines=(one(key="a"), one(key="b", markup_manual=D("0.10"))),
        mode=VersionPricingMode.MARKUP,
        markup_override=D("0.50"),
    )
    a, b = price_version(version, ctx()).lines
    assert (a.sale_total, a.markup_source) == (D("1500.00"), MarkupSource.VERSION)
    assert (b.sale_total, b.markup_source) == (D("1100.00"), MarkupSource.LINE)


def test_version_margin_mode_skips_locked_lines() -> None:
    version = VersionInput(
        lines=(one(key="a"), one(key="b", locked=True)),
        mode=VersionPricingMode.MARGIN,
        target_margin=D("0.50"),
    )
    a, b = price_version(version, ctx()).lines
    assert a.sale_total == D("2000.00")
    assert b.sale_total == D("1300.00")


def test_target_price_keeps_locked_lines_and_ignores_unlocked_discounts() -> None:
    version = VersionInput(
        lines=(
            one(key="fija", locked=True, markup_manual=D(0)),
            one(key="libre", discount_rate=D("0.50")),
        ),
        mode=VersionPricingMode.PRICE,
        target_price=D(5000),
    )
    fixed, free = price_version(version, ctx()).lines
    assert fixed.sale_total == D("1000.00")
    assert free.sale_total == D("4000.00")


def test_target_price_with_iva_and_rounding_warning() -> None:
    version = VersionInput(
        lines=(one(),),
        mode=VersionPricingMode.PRICE,
        target_price=D(1210),
        target_includes_iva=True,
    )
    assert price_version(version, ctx()).sale_subtotal == D("1000.00")
    odd = VersionInput(lines=(one(),), mode=VersionPricingMode.PRICE, target_price=D(1234))
    result = price_version(odd, ctx(rounding_increment=D(100)))
    assert result.sale_subtotal == D("1200.00")
    assert Warning_.TARGET_ROUNDED in result.warnings


@pytest.mark.parametrize(
    ("version", "code"),
    [
        (VersionInput(lines=(one(),), mode=VersionPricingMode.PRICE), "target_price_required"),
        (
            VersionInput(
                lines=(one(),),
                mode=VersionPricingMode.PRICE,
                target_price=D(10),
                global_discount_rate=D("0.1"),
            ),
            "target_with_discount",
        ),
        (
            VersionInput(
                lines=(one(unit_cost=D(0)),), mode=VersionPricingMode.PRICE, target_price=D(10)
            ),
            "target_no_cost_base",
        ),
        (VersionInput(lines=(one(),), mode=VersionPricingMode.MARGIN), "target_margin_required"),
        (
            VersionInput(lines=(one(),), mode=VersionPricingMode.MARKUP, markup_override=D(-1)),
            "markup_out_of_range",
        ),
        (VersionInput(lines=(one(),), global_discount_rate=D(1)), "discount_out_of_range"),
        (VersionInput(lines=(one(days=0),)), "days_positive"),
        (VersionInput(lines=(one(unit_cost=D(-1)),)), "cost_negative"),
        (VersionInput(lines=(one(discount_rate=D(1)),)), "discount_out_of_range"),
        (VersionInput(lines=(one(markup_manual=D(-1)),)), "markup_out_of_range"),
        (VersionInput(lines=(one(pricing_mode=LinePricingMode.PRICE),)), "target_price_required"),
        (VersionInput(lines=(one(pricing_mode=LinePricingMode.MARGIN),)), "target_margin_required"),
    ],
)
def test_invalid_inputs(version: VersionInput, code: str) -> None:
    with pytest.raises(PricingError) as excinfo:
        price_version(version, ctx())
    assert excinfo.value.code == code


def test_invalid_increment_and_fx() -> None:
    with pytest.raises(PricingError, match="incremento"):
        price_version(VersionInput(lines=(one(),)), ctx(rounding_increment=D(0)))
    version = VersionInput(lines=(one(),))
    result = price_version(version, ctx())
    with pytest.raises(PricingError) as excinfo:
        present_in_currency(result, version, ctx(), "USD", D(0))
    assert excinfo.value.code == "invalid_fx_rate"


def test_warnings_below_cost_and_min_margin() -> None:
    cheap = VersionInput(lines=(one(markup_manual=D("-0.10")),))
    assert Warning_.BELOW_COST in price_version(cheap, ctx()).warnings
    thin = VersionInput(lines=(one(markup_manual=D("0.05")),))
    result = price_version(thin, ctx(min_margin=D("0.20")))
    assert result.warnings == (Warning_.BELOW_MIN_MARGIN,)
    assert price_version(thin, ctx(min_margin=D("0.01"))).warnings == ()


def test_effective_cost_by_tax_condition() -> None:
    gross = one(unit_cost=D(1210), cost_includes_iva=True)
    net = one(unit_cost=D(1000))
    assert effective_unit_cost(gross, TaxCondition.RI) == D(1000)
    assert effective_unit_cost(net, TaxCondition.RI) == D(1000)
    assert effective_unit_cost(gross, TaxCondition.EXENTO) == D(1210)
    assert effective_unit_cost(net, TaxCondition.MONOTRIBUTO) == D(1210)
    no_iva_supplier = one(unit_cost=D(1000), cost_iva_rate=D(0))
    assert effective_unit_cost(no_iva_supplier, TaxCondition.MONOTRIBUTO) == D(1000)


def test_zero_sale_has_no_margin_and_result_carries_engine_version() -> None:
    version = VersionInput(
        lines=(one(unit_cost=D(0), pricing_mode=LinePricingMode.PRICE, target_price=D(0)),)
    )
    result = price_version(version, ctx())
    assert result.lines[0].margin is None
    assert result.margin_net is None
    assert result.markup is None
    assert result.engine_version == ENGINE_VERSION
