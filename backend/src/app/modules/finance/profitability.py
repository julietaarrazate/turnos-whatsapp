"""Rentabilidad del evento (O-06) y desvíos (O-05): cálculo puro, sin base de datos.

Ganancia = venta neta − costo − cargos sobre la venta (PRODUCT_SPEC §8). Los cargos sobre la
venta (IIBB, etc.) son los de la versión aceptada: dependen de la venta, no de los gastos.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

RATE = Decimal("0.000001")


@dataclass(frozen=True)
class Result:
    sale_net: Decimal
    cost: Decimal
    sale_charges: Decimal
    profit: Decimal
    margin: Decimal | None  # ganancia / venta neta


def _rate(value: Decimal) -> Decimal:
    return value.quantize(RATE, rounding=ROUND_HALF_UP)


def result(sale_net: Decimal, cost: Decimal, sale_charges: Decimal) -> Result:
    profit = sale_net - cost - sale_charges
    return Result(
        sale_net=sale_net,
        cost=cost,
        sale_charges=sale_charges,
        profit=profit,
        margin=_rate(profit / sale_net) if sale_net > 0 else None,
    )


def deviation(budgeted: Decimal, actual: Decimal) -> tuple[Decimal, Decimal | None]:
    """Desvío de costo: (real − presupuestado) y su proporción sobre lo presupuestado."""
    delta = actual - budgeted
    return delta, _rate(delta / budgeted) if budgeted else None
