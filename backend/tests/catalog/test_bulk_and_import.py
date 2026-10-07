"""Aumento masivo (C-10) e importación del catálogo desde XLSX/CSV (C-09)."""

from base64 import b64encode
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core.enums import Role
from app.core.spreadsheet import parse_decimal_ar
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", "1234.56"),
        ("$ 1.500", "1500"),
        ("1,5", "1.5"),
        ("12.75", "12.75"),
        ("1,234.5", "1234.5"),
        ("1.234.567", "1234567"),
        ("-3", "-3"),
        (12, "12"),
        (3.5, "3.5"),
        ("abc", None),
        ("1,2,3", None),
        ("", None),
    ],
)
def test_parse_decimal_ar(raw: Any, expected: str | None) -> None:
    result = parse_decimal_ar(raw)
    assert result == (Decimal(expected) if expected is not None else None)


def _product(client: TestClient, world: OrgWorld) -> dict[str, Any]:
    return _ok(client.get(f"/api/v1/products/{world.ids['product_id']}"))


def test_bulk_increase_by_supplier_appends_history_and_leaves_budgets_alone() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    sent_before = _ok(owner.get(f"/api/v1/budgets/{world.ids['sent_budget_id']}"))["version"]
    body = {"supplier_id": str(world.ids["supplier_id"]), "rate": "0.08"}

    preview = _ok(owner.post("/api/v1/catalog/bulk-increase/preview", json=body))
    [item] = [i for i in preview["items"] if i["product_name"] == "Producto ejemplo"]
    assert (item["current"], item["new"]) == ("1000.00", "1080.00")
    assert preview["scope"] == "proveedor Proveedor ejemplo"
    # La vista previa no guarda nada.
    offer = _product(owner, world)["offers"][0]
    assert Decimal(offer["current_cost"]["amount"]) == Decimal(1000)

    _ok(owner.post("/api/v1/catalog/bulk-increase", json=body))
    offer = _product(owner, world)["offers"][0]
    assert Decimal(offer["current_cost"]["amount"]) == Decimal(1080)
    history = _ok(owner.get(f"/api/v1/offers/{offer['id']}/prices"))
    assert [h["source"] for h in history][:2] == ["BULK_UPDATE", "MANUAL"]  # no pisa el anterior
    assert history[0]["source_ref"].startswith("Aumento +8.00 %")
    # Lo enviado no cambia (la línea tiene el costo copiado).
    sent_after = _ok(owner.get(f"/api/v1/budgets/{world.ids['sent_budget_id']}"))["version"]
    assert sent_after["sale_net"] == sent_before["sale_net"]


def test_bulk_increase_by_category_validation_and_permissions() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    body = {"category_id": str(world.ids["product_category_id"]), "rate": "-0.10"}
    preview = _ok(owner.post("/api/v1/catalog/bulk-increase/preview", json=body))
    assert [i["new"] for i in preview["items"]] == ["900.00"]
    empty = owner.post("/api/v1/catalog/bulk-increase/preview", json={"rate": "0.1"})
    assert empty.status_code == 422
    nothing = owner.post(
        "/api/v1/catalog/bulk-increase",
        json={"category_id": str(world.ids["category_id"]), "rate": "0.1"},
    )
    assert (nothing.status_code, nothing.json()["code"]) == (422, "bulk_nothing_to_update")
    quoter = logged_in(world.members[Role.QUOTER])
    assert quoter.post("/api/v1/catalog/bulk-increase/preview", json=body).status_code == 403


HEADERS = ["Producto", "Categoría", "Proveedor", "Unidad", "Costo", "Incluye IVA", "Detalle"]


def _xlsx(rows: list[list[Any]]) -> str:
    workbook = Workbook()
    workbook.active.append(["Lista de precios octubre"])  # título arriba del encabezado
    workbook.active.append(HEADERS)
    for row in rows:
        workbook.active.append(row)
    out = BytesIO()
    workbook.save(out)
    return b64encode(out.getvalue()).decode()


ROWS: list[list[Any]] = [
    ["Pantalla LED 3x2", "Técnica", "Rental Pro", "u", 150000, "sí", "Con operador"],
    ["Producto ejemplo", None, "Proveedor ejemplo", None, "1.250,50", "no", None],
    ["Vallas", "Estructura", "Rental Pro", "kilos", 100, None, None],  # unidad desconocida
    [None, "Técnica", "X", "u", 10, None, None],  # sin nombre
    ["Mesa", "Mobiliario", None, "u", 5000, None, None],  # costo sin proveedor
    ["Pantalla LED 3x2", "Técnica", "Rental Pro", "u", 1, None, None],  # repetida
    ["Flete", None, None, "viaje", None, None, None],  # solo el producto
]


def test_catalog_import_preview_apply_and_reimport() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    body = {"file_base64": _xlsx(ROWS), "filename": "lista.xlsx"}

    preview = _ok(owner.post("/api/v1/catalog/import/preview", json=body))
    assert preview["headers"][:3] == ["Producto", "Categoría", "Proveedor"]
    assert preview["mapping"]["name"] == 0
    assert preview["mapping"]["cost"] == 4
    assert preview["mapping"]["description_client"] == 6
    by_row = {r["row"]: r for r in preview["rows"]}
    assert by_row[3]["action"] == "CREATE"
    assert by_row[4]["action"] == "UPDATE"  # ya existe
    assert by_row[5]["errors"] == ["Unidad desconocida: kilos"]
    assert by_row[6]["errors"] == ["Falta el nombre del producto"]
    assert by_row[7]["errors"] == ["Un costo necesita proveedor"]
    assert by_row[8]["errors"] == ["Repetida (igual a la fila 3)"]
    summary = preview["summary"]
    assert (summary["rows"], summary["valid"], summary["errors"]) == (7, 3, 4)
    assert (summary["products_new"], summary["suppliers_new"], summary["costs"]) == (2, 1, 2)
    assert preview["applied"] is False
    found = _ok(owner.get("/api/v1/products", params={"q": "Pantalla"}))["items"]
    assert found == []  # la vista previa no guarda nada

    applied = _ok(owner.post("/api/v1/catalog/import", json=body))
    assert (applied["applied"], applied["summary"]["costs"]) == (True, 2)
    [screen] = _ok(owner.get("/api/v1/products", params={"q": "Pantalla"}))["items"]
    detail = _ok(owner.get(f"/api/v1/products/{screen['id']}"))
    assert detail["description_client"] == "Con operador"
    [offer] = detail["offers"]
    assert offer["supplier_name"] == "Rental Pro"
    cost = offer["current_cost"]
    assert (Decimal(cost["amount"]), cost["includes_iva"]) == (Decimal(150000), True)
    example = _product(owner, world)["offers"][0]
    assert Decimal(example["current_cost"]["amount"]) == Decimal("1250.50")
    prices = _ok(owner.get(f"/api/v1/offers/{example['id']}/prices"))
    assert prices[0]["source"] == "IMPORT"

    # Reimportar el mismo archivo no duplica productos ni costos.
    again = _ok(owner.post("/api/v1/catalog/import", json=body))
    assert again["summary"]["costs"] == 0
    assert len(_ok(owner.get("/api/v1/products", params={"q": "Pantalla"}))["items"]) == 1


def test_csv_with_semicolons_and_permissions() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    text = 'Producto;Proveedor;Costo\nAudio chico;Sonido Sur;"1.234,56"\n'
    body = {"file_base64": b64encode(text.encode("latin-1")).decode(), "filename": "lista.csv"}
    applied = _ok(owner.post("/api/v1/catalog/import", json=body))
    assert applied["summary"]["valid"] == 1
    [product] = _ok(owner.get("/api/v1/products", params={"q": "Audio chico"}))["items"]
    detail = _ok(owner.get(f"/api/v1/products/{product['id']}"))
    assert Decimal(detail["offers"][0]["current_cost"]["amount"]) == Decimal("1234.56")
    categories = {c["id"]: c["name"] for c in _ok(owner.get("/api/v1/categories"))}
    assert categories[detail["category_id"]] == "Sin categoría"

    bad = owner.post(
        "/api/v1/catalog/import/preview", json={"file_base64": "nope!!", "filename": "x.xlsx"}
    )
    assert bad.status_code == 422
    quoter = logged_in(world.members[Role.QUOTER])
    assert quoter.post("/api/v1/catalog/import/preview", json=body).status_code == 403
