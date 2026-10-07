"""Propiedades del motor (ARCHITECTURE §13.2), probadas con miles de casos aleatorios."""

from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.domain.pricing import (
    LineInput,
    LinePricingMode,
    MarkupRule,
    PricingContext,
    SaleCharge,
    TaxCondition,
    VersionInput,
    VersionPricingMode,
    Warning_,
    present_in_currency,
    price_version,
)

money = st.decimals(min_value=Decimal("100"), max_value=Decimal("50000000"), places=2)
qty = st.decimals(min_value=Decimal("1"), max_value=Decimal("500"), places=2)
markups = st.decimals(min_value=Decimal("0"), max_value=Decimal("3"), places=4)
rates = st.decimals(min_value=Decimal("0"), max_value=Decimal("0.5"), places=4)
increments = st.sampled_from([Decimal("0.01"), Decimal("1"), Decimal("100"), Decimal("1000")])


def ctx(increment: Decimal = Decimal("0.01"), charges: Decimal = Decimal(0)) -> PricingContext:
    return PricingContext(
        tax_condition=TaxCondition.RI,
        org_rule=MarkupRule(Decimal("0.30")),
        sale_charges=(SaleCharge("IIBB", charges),) if charges else (),
        rounding_increment=increment,
    )


lines_strategy = st.lists(
    st.builds(
        lambda i, c, q, m: LineInput(key=f"l{i}", quantity=q, unit_cost=c, markup_manual=m),
        st.integers(0, 10_000),
        money,
        qty,
        markups,
    ),
    min_size=1,
    max_size=12,
    unique_by=lambda line: line.key,
)


@settings(max_examples=300)
@given(lines_strategy, rates, rates, increments)
def test_visible_amounts_always_add_up(
    lines: list[LineInput], discount: Decimal, fee: Decimal, increment: Decimal
) -> None:
    version = VersionInput(
        lines=tuple(lines), global_discount_rate=discount, management_fee_rate=fee
    )
    result = price_version(version, ctx(increment))
    assert sum(line.sale_total for line in result.lines) == result.sale_subtotal
    assert sum(line.allocated_global_discount for line in result.lines) == result.global_discount
    assert result.sale_net == result.sale_subtotal - result.global_discount + result.management_fee
    assert result.total == result.sale_net + result.iva


@settings(max_examples=300)
@given(money, qty, markups)
def test_margin_equals_markup_over_one_plus_markup(cost: Decimal, q: Decimal, m: Decimal) -> None:
    line = LineInput(key="a", quantity=q, unit_cost=cost, markup_manual=m)
    priced = price_version(VersionInput(lines=(line,)), ctx()).lines[0]
    assert priced.markup_applied is not None
    assert priced.margin is not None
    expected = priced.markup_applied / (1 + priced.markup_applied)
    assert abs(priced.margin - expected) <= Decimal("0.000002")


@settings(max_examples=300)
@given(lines_strategy, st.integers(min_value=1, max_value=10_000), increments)
def test_target_price_is_hit_exactly(
    lines: list[LineInput], target_units: int, increment: Decimal
) -> None:
    target = Decimal(target_units) * Decimal(1000)  # múltiplo de cualquier incremento probado
    version = VersionInput(lines=tuple(lines), mode=VersionPricingMode.PRICE, target_price=target)
    result = price_version(version, ctx(increment))
    assert result.sale_subtotal == target
    assert all(line.sale_total % increment == 0 for line in result.lines)


@settings(max_examples=300)
@given(lines_strategy, st.integers(min_value=1, max_value=10_000), rates, increments)
def test_target_price_with_fee_lands_within_rounding(
    lines: list[LineInput], target_units: int, fee: Decimal, increment: Decimal
) -> None:
    """El objetivo incluye el fee: los ítems son múltiplos del incremento y el fee va al
    centavo, así que el neto queda a menos de medio incremento (más el centavo) del objetivo."""
    target = Decimal(target_units) * Decimal(1000)
    version = VersionInput(
        lines=tuple(lines),
        mode=VersionPricingMode.PRICE,
        target_price=target,
        management_fee_rate=fee,
    )
    result = price_version(version, ctx(increment))
    assert abs(result.sale_net - target) <= increment * (1 + fee) / 2 + Decimal("0.005")
    assert (result.sale_net != target) == (Warning_.TARGET_ROUNDED in result.warnings)


@settings(max_examples=300)
@given(money, st.decimals(min_value=Decimal("0"), max_value=Decimal("0.6"), places=3), rates)
def test_target_margin_is_net_of_sale_charges(cost: Decimal, g: Decimal, c: Decimal) -> None:
    assume(g + c < Decimal("0.95"))  # g + c ≥ 1 no tiene precio posible (ver test_engine)
    line = LineInput(
        key="a",
        quantity=Decimal(1),
        unit_cost=cost,
        pricing_mode=LinePricingMode.MARGIN,
        target_margin=g,
    )
    result = price_version(VersionInput(lines=(line,)), ctx(charges=c))
    assert result.margin_net is not None
    # El redondeo a centavos mueve el margen a lo sumo ~1 centavo sobre el precio.
    assert abs(result.margin_net - g) <= Decimal("0.0001")


@settings(max_examples=200)
@given(money, qty, qty, markups)
def test_more_quantity_never_costs_less(
    cost: Decimal, q1: Decimal, q2: Decimal, m: Decimal
) -> None:
    low, high = sorted((q1, q2))

    def price(q: Decimal) -> tuple[Decimal, Decimal]:
        line = LineInput("a", q, cost, markup_manual=m)
        priced = price_version(VersionInput(lines=(line,)), ctx()).lines[0]
        return priced.cost_total, priced.sale_total

    assert price(low)[0] <= price(high)[0]
    assert price(low)[1] <= price(high)[1]


@settings(max_examples=200)
@given(money, markups, markups)
def test_more_markup_never_sells_for_less(cost: Decimal, m1: Decimal, m2: Decimal) -> None:
    low, high = sorted((m1, m2))

    def price(m: Decimal) -> Decimal:
        line = LineInput("a", Decimal(1), cost, markup_manual=m)
        return price_version(VersionInput(lines=(line,)), ctx()).lines[0].sale_total

    assert price(low) <= price(high)


@settings(max_examples=200)
@given(lines_strategy, st.decimals(min_value=Decimal("100"), max_value=Decimal("2000"), places=2))
def test_presentation_in_usd_adds_up(lines: list[LineInput], fx: Decimal) -> None:
    version = VersionInput(lines=tuple(lines), global_discount_rate=Decimal("0.05"))
    context = ctx()
    result = price_version(version, context)
    presentation = present_in_currency(result, version, context, "USD", fx)
    assert sum(presentation.lines.values()) == presentation.subtotal
    assert presentation.net == presentation.subtotal - presentation.global_discount
    assert presentation.total == presentation.net + presentation.iva
