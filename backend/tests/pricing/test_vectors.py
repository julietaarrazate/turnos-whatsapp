"""Vectores dorados (vectors.json). Cualquier implementación del motor debe pasarlos."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.domain.pricing import PricingError, present_in_currency, price_version
from tests.pricing import builders

VECTORS: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "vectors.json").read_text(encoding="utf-8")
)["vectors"]


def _same(actual: object, expected: object) -> bool:
    if expected is None:
        return actual is None
    if isinstance(actual, Decimal):
        return actual == Decimal(str(expected))
    return str(actual) == str(expected)


@pytest.mark.parametrize("vector", VECTORS, ids=[v["id"] for v in VECTORS])
def test_vector(vector: dict[str, Any]) -> None:
    ctx = builders.context(vector["context"])
    version = builders.version(vector["version"])
    if "error" in vector:
        with pytest.raises(PricingError) as excinfo:
            price_version(version, ctx)
        assert excinfo.value.code == vector["error"]
        return

    result = price_version(version, ctx)
    expected = vector["expected"]
    lines = {line.key: line for line in result.lines}
    for key, fields in expected.get("lines", {}).items():
        for field, value in fields.items():
            actual = getattr(lines[key], field)
            assert _same(actual, value), f"{vector['id']} {key}.{field}: {actual} != {value}"
    for field, value in expected.get("totals", {}).items():
        actual = getattr(result, field)
        assert _same(actual, value), f"{vector['id']} {field}: {actual} != {value}"

    # Invariantes que valen para todo vector.
    assert sum(line.sale_total for line in result.lines) == result.sale_subtotal
    assert sum(line.allocated_global_discount for line in result.lines) == result.global_discount
    assert result.total == result.sale_net + result.iva

    if "present" in vector:
        present = vector["present"]
        presentation = present_in_currency(
            result, version, ctx, present["currency"], Decimal(present["fx_rate"])
        )
        exp = expected["presentation"]
        for key, value in exp["lines"].items():
            assert presentation.lines[key] == Decimal(value), key
        for field in ("subtotal", "iva", "total"):
            assert getattr(presentation, field) == Decimal(exp[field]), field
        assert sum(presentation.lines.values()) == presentation.subtotal
