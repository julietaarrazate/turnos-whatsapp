"""Motor de pricing (DOMAIN_MODEL §5 — especificación normativa).

Funciones puras y deterministas: sin I/O, sin reloj y sin floats. Lo que el cliente ve
(importes de línea, subtotal, total) siempre suma exacto.
"""

from dataclasses import replace
from decimal import Decimal

from app.domain.pricing.inputs import LineInput, MarkupRule, PricingContext, VersionInput
from app.domain.pricing.outputs import ChargeAmount, LinePriced, Presentation, VersionPriced
from app.domain.pricing.rounding import allocate, r2, r_inc, rate
from app.domain.pricing.types import (
    CENT,
    ONE,
    ZERO,
    ChargeMode,
    LinePricingMode,
    MarkupSource,
    PricingError,
    RuleMode,
    TaxCondition,
    VersionPricingMode,
    Warning_,
)

ENGINE_VERSION = "1.0.0"


# --- Validación ---------------------------------------------------------------------------


def _validate_line(line: LineInput) -> None:
    if line.quantity <= ZERO:
        raise PricingError("quantity_positive", f"{line.key}: la cantidad debe ser mayor a 0")
    if line.days < 1:
        raise PricingError("days_positive", f"{line.key}: los días deben ser al menos 1")
    if line.unit_cost < ZERO:
        raise PricingError("cost_negative", f"{line.key}: el costo no puede ser negativo")
    if not ZERO <= line.discount_rate < ONE:
        raise PricingError("discount_out_of_range", f"{line.key}: descuento entre 0 y 100 %")
    if line.markup_manual is not None and line.markup_manual <= -ONE:
        raise PricingError("markup_out_of_range", f"{line.key}: el markup debe ser mayor a -100 %")


def _charges_rate(ctx: PricingContext) -> Decimal:
    return sum((c.rate for c in ctx.sale_charges), ZERO)


# --- Línea (L1–L8) ---------------------------------------------------------------------


def effective_unit_cost(line: LineInput, tax_condition: TaxCondition) -> Decimal:
    """L1: un RI computa el costo neto de IVA (crédito fiscal); los demás, el costo con IVA."""
    iva = ONE + line.cost_iva_rate
    if tax_condition is TaxCondition.RI:
        return line.unit_cost / iva if line.cost_includes_iva else line.unit_cost
    return line.unit_cost if line.cost_includes_iva else line.unit_cost * iva


def _rule_markup(rule: MarkupRule) -> Decimal:
    if rule.mode is RuleMode.MARGIN:
        if not ZERO <= rule.value < ONE:
            raise PricingError("margin_out_of_range", "El margen debe estar entre 0 y 100 %")
        return rule.value / (ONE - rule.value)
    return rule.value


def resolve_markup(
    line: LineInput, version_markup: Decimal | None, ctx: PricingContext
) -> tuple[Decimal, MarkupSource, str | None]:
    """Cadena de precedencia (§5.3): línea > versión > cliente > producto > categoría > org."""
    if line.markup_manual is not None:
        return line.markup_manual, MarkupSource.LINE, None
    if version_markup is not None:
        return version_markup, MarkupSource.VERSION, None
    if line.resolved is not None:
        return line.resolved.value, line.resolved.source, line.resolved.source_id
    candidates: list[tuple[MarkupRule | None, MarkupSource]] = [
        (ctx.client_rule, MarkupSource.CLIENT),
        (line.product_rule, MarkupSource.PRODUCT),
        *((rule, MarkupSource.CATEGORY) for rule in line.category_rules),
        (ctx.org_rule, MarkupSource.ORG),
    ]
    for rule, source in candidates:
        if rule is not None:
            return _rule_markup(rule), source, rule.source_id
    raise AssertionError("unreachable: org_rule siempre existe")  # pragma: no cover


def _target_margin_price(cost: Decimal, margin: Decimal, ctx: PricingContext) -> Decimal:
    """P = C / (1 − g − c): el margen después de los cargos sobre la venta es g."""
    charges = _charges_rate(ctx) if ctx.margin_includes_sale_charges else ZERO
    if margin < ZERO or margin + charges >= ONE:
        raise PricingError(
            "margin_out_of_range", "El margen objetivo más los cargos debe ser menor a 100 %"
        )
    return r_inc(cost / (ONE - margin - charges), ctx.rounding_increment)


def _ratios(cost: Decimal, sale: Decimal) -> tuple[Decimal | None, Decimal | None]:
    profit = sale - cost
    markup = rate(profit / cost) if cost > ZERO else None
    margin = rate(profit / sale) if sale > ZERO else None
    return markup, margin


def price_line(
    line: LineInput, ctx: PricingContext, version_markup: Decimal | None = None
) -> LinePriced:
    _validate_line(line)
    unit_cost = effective_unit_cost(line, ctx.tax_condition)  # L1 (L2: moneda base, D-09)
    duration = line.days if line.charge_mode is ChargeMode.PER_DAY else 1  # L3
    cost = r2(unit_cost * line.quantity * duration)  # L4
    source_id: str | None = None

    if line.pricing_mode is LinePricingMode.PRICE:
        if line.target_price is None or line.target_price < ZERO:
            raise PricingError("target_price_required", f"{line.key}: falta el precio objetivo")
        list_total = r2(line.target_price)
        source = MarkupSource.TARGET_PRICE
    elif line.pricing_mode is LinePricingMode.MARGIN:
        if line.target_margin is None:
            raise PricingError("target_margin_required", f"{line.key}: falta el margen objetivo")
        list_total = _target_margin_price(cost, line.target_margin, ctx)
        source = MarkupSource.TARGET_MARGIN
    else:
        markup, source, source_id = resolve_markup(line, version_markup, ctx)  # L5
        list_total = r_inc(cost * (ONE + markup), ctx.rounding_increment)  # L6

    sale = (  # L7
        r_inc(list_total * (ONE - line.discount_rate), ctx.rounding_increment)
        if line.discount_rate
        else list_total
    )
    markup_applied, margin = _ratios(cost, sale)  # L8
    return LinePriced(
        key=line.key,
        unit_cost_effective=unit_cost,
        cost_total=cost,
        markup_applied=markup_applied,
        markup_source=source,
        markup_source_id=source_id,
        sale_list_total=list_total,
        sale_total=sale,
        profit=sale - cost,
        margin=margin,
        allocated_global_discount=ZERO,
    )


# --- Versión (V1–V7, §5.5–5.6) ---------------------------------------------------------


def _with_mode(line: LineInput, mode: LinePricingMode, **values: object) -> LineInput:
    return replace(line, pricing_mode=mode, discount_rate=ZERO, **values)  # type: ignore[arg-type]


def _price_target(
    version: VersionInput, ctx: PricingContext, warnings: list[Warning_]
) -> list[LinePriced]:
    """§5.6: markup uniforme sobre las líneas no bloqueadas; el residuo se reparte por mayor
    resto en incrementos, así el total da exacto."""
    if version.target_price is None or version.target_price <= ZERO:
        raise PricingError("target_price_required", "Falta el precio objetivo")
    if version.global_discount_rate:
        raise PricingError(
            "target_with_discount", "El precio objetivo no se combina con un descuento global"
        )
    inc = ctx.rounding_increment
    target = version.target_price
    if version.target_includes_iva and ctx.tax_condition is TaxCondition.RI:
        target = target / (ONE + ctx.default_iva_rate)
    rounded = r_inc(target, inc)
    if rounded != target:
        warnings.append(Warning_.TARGET_ROUNDED)
    target = rounded

    priced: dict[int, LinePriced] = {}
    for i, line in enumerate(version.lines):
        if line.locked:
            priced[i] = price_line(line, ctx)
    unlocked = [i for i, line in enumerate(version.lines) if not line.locked]
    costs = {
        i: price_line(
            _with_mode(version.lines[i], LinePricingMode.MARKUP, markup_manual=ZERO), ctx
        ).cost_total
        for i in unlocked
    }
    remaining = target - sum((p.sale_total for p in priced.values()), ZERO)
    cost_base = sum(costs.values(), ZERO)
    if remaining < ZERO:
        raise PricingError(
            "target_below_locked", "El precio objetivo es menor que las líneas bloqueadas"
        )
    if cost_base == ZERO:
        raise PricingError(
            "target_no_cost_base", "No hay líneas desbloqueadas con costo para repartir"
        )
    shares = allocate(remaining, [costs[i] for i in unlocked], inc)
    for i, share in zip(unlocked, shares, strict=True):
        line = _with_mode(version.lines[i], LinePricingMode.PRICE, target_price=share)
        priced[i] = price_line(line, ctx)
    return [priced[i] for i in range(len(version.lines))]


def _price_lines(
    version: VersionInput, ctx: PricingContext, warnings: list[Warning_]
) -> list[LinePriced]:
    if version.mode is VersionPricingMode.PRICE:
        return _price_target(version, ctx, warnings)
    if version.mode is VersionPricingMode.MARGIN:
        if version.target_margin is None:
            raise PricingError("target_margin_required", "Falta el margen objetivo")
        return [
            price_line(line, ctx)
            if line.locked
            else price_line(
                replace(
                    line,
                    pricing_mode=LinePricingMode.MARGIN,
                    target_margin=version.target_margin,
                ),
                ctx,
            )
            for line in version.lines
        ]
    version_markup = version.markup_override if version.mode is VersionPricingMode.MARKUP else None
    if version_markup is not None and version_markup <= -ONE:
        raise PricingError("markup_out_of_range", "El markup debe ser mayor a -100 %")
    return [price_line(line, ctx, version_markup) for line in version.lines]


def _iva(nets: list[Decimal], iva_rates: list[Decimal], tax_condition: TaxCondition) -> Decimal:
    """V6: por alícuota sobre la venta neta (ya descontado el descuento global)."""
    if tax_condition is not TaxCondition.RI:
        return ZERO
    by_rate: dict[Decimal, Decimal] = {}
    for net, iva_rate in zip(nets, iva_rates, strict=True):
        by_rate[iva_rate] = by_rate.get(iva_rate, ZERO) + net
    return sum((r2(base * iva_rate) for iva_rate, base in by_rate.items()), ZERO)


def price_version(version: VersionInput, ctx: PricingContext) -> VersionPriced:
    if not ZERO <= version.global_discount_rate < ONE:
        raise PricingError("discount_out_of_range", "El descuento global va entre 0 y 100 %")
    if ctx.rounding_increment <= ZERO:
        raise PricingError("invalid_increment", "El incremento de redondeo debe ser positivo")
    warnings: list[Warning_] = []
    lines = _price_lines(version, ctx, warnings)

    subtotal = sum((line.sale_total for line in lines), ZERO)  # V1
    discount = r2(subtotal * version.global_discount_rate)  # V2
    allocated = allocate(discount, [line.sale_total for line in lines], CENT)
    lines = [
        replace(line, allocated_global_discount=share)
        for line, share in zip(lines, allocated, strict=True)
    ]
    net = subtotal - discount
    charges = tuple(  # V3
        ChargeAmount(c.name, c.rate, r2(net * c.rate)) for c in ctx.sale_charges
    )
    charges_total = sum((c.amount for c in charges), ZERO)
    cost_direct = sum((line.cost_total for line in lines), ZERO)  # V4
    profit = net - cost_direct - charges_total  # V5
    markup, margin_gross = _ratios(cost_direct, net)
    margin_net = rate(profit / net) if net > ZERO else None
    iva = _iva(  # V6
        [line.sale_total - line.allocated_global_discount for line in lines],
        [line.iva_rate for line in version.lines],
        ctx.tax_condition,
    )

    if profit < ZERO or any(line.profit < ZERO for line in lines):
        warnings.append(Warning_.BELOW_COST)
    if ctx.min_margin is not None and margin_net is not None and margin_net < ctx.min_margin:
        warnings.append(Warning_.BELOW_MIN_MARGIN)

    return VersionPriced(
        lines=tuple(lines),
        cost_direct=cost_direct,
        sale_subtotal=subtotal,
        global_discount=discount,
        sale_net=net,
        sale_charges=charges,
        sale_charges_total=charges_total,
        cost_total=cost_direct + charges_total,
        profit=profit,
        markup=markup,
        margin_gross=margin_gross,
        margin_net=margin_net,
        iva=iva,
        total=net + iva,  # V7
        warnings=tuple(dict.fromkeys(warnings)),
        engine_version=ENGINE_VERSION,
    )


# --- Presentación en otra moneda (D-09) ---------------------------------------------------


def present_in_currency(
    result: VersionPriced,
    version: VersionInput,
    ctx: PricingContext,
    currency: str,
    fx_rate: Decimal,
) -> Presentation:
    """Convierte lo que ve el cliente con un tipo de cambio congelado (base por 1 unidad).

    Se convierte el subtotal y se reparte entre las líneas por mayor resto, así la propuesta
    en la otra moneda también suma exacto. El descuento y el IVA se recalculan en esa moneda.
    """
    if fx_rate <= ZERO:
        raise PricingError("invalid_fx_rate", "El tipo de cambio debe ser positivo")
    subtotal = r2(result.sale_subtotal / fx_rate)
    line_amounts = allocate(subtotal, [line.sale_total for line in result.lines], CENT)
    discount = r2(subtotal * version.global_discount_rate)
    allocated = allocate(discount, line_amounts, CENT)
    net = subtotal - discount
    iva = _iva(
        [amount - share for amount, share in zip(line_amounts, allocated, strict=True)],
        [line.iva_rate for line in version.lines],
        ctx.tax_condition,
    )
    return Presentation(
        currency=currency,
        fx_rate=fx_rate,
        lines={line.key: amount for line, amount in zip(result.lines, line_amounts, strict=True)},
        subtotal=subtotal,
        global_discount=discount,
        net=net,
        iva=iva,
        total=net + iva,
    )


__all__ = [
    "ENGINE_VERSION",
    "effective_unit_cost",
    "present_in_currency",
    "price_line",
    "price_version",
    "resolve_markup",
]
