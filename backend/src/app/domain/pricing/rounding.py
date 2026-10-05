"""Único lugar del motor donde se redondea (DOMAIN_MODEL §5.1). Siempre HALF_UP."""

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from app.domain.pricing.types import CENT, ZERO

RATE_QUANTUM = Decimal("0.000001")


def r2(value: Decimal) -> Decimal:
    """A centavos."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def r_inc(value: Decimal, increment: Decimal) -> Decimal:
    """Al incremento comercial (0,01 · 1 · 10 · 100 · 1.000), HALF_UP."""
    units = (value / increment).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return r2(units * increment)


def floor_inc(value: Decimal, increment: Decimal) -> Decimal:
    units = (value / increment).to_integral_value(rounding=ROUND_FLOOR)
    return r2(units * increment)


def rate(value: Decimal) -> Decimal:
    """Tasas (markup, margen) con 6 decimales: 0.230769 = 23,0769 %."""
    return value.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)


def allocate(total: Decimal, weights: list[Decimal], unit: Decimal) -> list[Decimal]:
    """Reparte ``total`` en múltiplos de ``unit`` proporcional a ``weights`` (mayor resto).

    Invariante: la suma del reparto es exactamente ``total`` (si ``total`` es múltiplo de
    ``unit``). Desempate: mayor peso, después el orden original.
    """
    weight_sum = sum(weights, ZERO)
    if ZERO in (weight_sum, total):
        return [ZERO for _ in weights]
    raw = [total * w / weight_sum for w in weights]
    shares = [floor_inc(r, unit) for r in raw]
    remaining = int(((total - sum(shares, ZERO)) / unit).to_integral_value())
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - shares[i]), -weights[i], i))
    for i in order[:remaining]:
        shares[i] += unit
    return shares
