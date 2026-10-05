"""Infraestructura de los tests de seguridad que recorren TODAS las rutas de la API.

Cuando un módulo nuevo agrega una ruta con parámetros o con body, estos tests fallan hasta
que se registre acá cómo obtener un ID válido (``PARAM_FACTORIES``) y un body de ejemplo
(``SAMPLE_BODIES``). Así ninguna ruta nueva queda fuera de la verificación.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.routing import BaseRoute

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.core.permissions import Permission
from app.main import create_app
from app.modules.auth import create_invitation
from app.modules.auth.dependencies import ACCESS_MARKER
from app.modules.catalog.models import (
    Category,
    PriceHistory,
    Product,
    Supplier,
    SupplierProduct,
    Unit,
)
from app.modules.clients import Client
from app.modules.pricing.models import MarkupRuleRow, SaleChargeRow
from tests.factories import DEFAULT_PASSWORD, Member, add_member, create_org, create_user


@dataclass
class OrgWorld:
    organization_id: UUID
    members: dict[Role, Member]
    target: Member  # un miembro extra sobre el que se actúa (cambiar rol, desactivar)
    invitation_id: UUID
    ids: dict[str, UUID] = field(default_factory=dict)  # entidades de negocio de ejemplo


def build_org(prefix: str) -> OrgWorld:
    org_id = create_org(f"Org {prefix}")
    members = {
        role: add_member(org_id, create_user(email), email, role)
        for role in Role
        for email in [f"{role.value.lower()}@{prefix}.example.com"]
    }
    target_email = f"target@{prefix}.example.com"
    target = add_member(org_id, create_user(target_email), target_email, Role.VIEWER)
    with session_scope(DbContext(organization_id=org_id)) as s:
        invitation, _ = create_invitation(
            s, org_id, f"pending@{prefix}.example.com", Role.QUOTER, None
        )
        invitation_id = invitation.id
        ids = _business_entities(s, org_id)
    return OrgWorld(org_id, members, target, invitation_id, ids)


def _business_entities(s: Any, org_id: UUID) -> dict[str, UUID]:
    """Una entidad de cada tipo, borrables sin conflictos (la categoría no tiene productos)."""
    unit_id = s.execute(select(Unit.id).where(Unit.code == "u")).scalar_one()
    client = Client(organization_id=org_id, name="Cliente ejemplo")
    category = Category(organization_id=org_id, name="Categoría vacía")
    product_category = Category(organization_id=org_id, name="Categoría con productos")
    supplier = Supplier(organization_id=org_id, name="Proveedor ejemplo")
    other_supplier = Supplier(organization_id=org_id, name="Otro proveedor")
    s.add_all([client, category, product_category, supplier, other_supplier])
    s.flush()
    product = Product(
        organization_id=org_id,
        name="Producto ejemplo",
        category_id=product_category.id,
        unit_id=unit_id,
    )
    s.add(product)
    s.flush()
    offer = SupplierProduct(
        organization_id=org_id, product_id=product.id, supplier_id=supplier.id, is_preferred=True
    )
    s.add(offer)
    s.flush()
    s.add(
        PriceHistory(
            organization_id=org_id,
            supplier_product_id=offer.id,
            amount=Decimal("1000"),
            valid_from=date(2026, 1, 1),
        )
    )
    rule = MarkupRuleRow(
        organization_id=org_id,
        scope="CATEGORY",
        scope_id=product_category.id,
        mode="MARKUP",
        value=Decimal("0.4"),
    )
    charge = SaleChargeRow(organization_id=org_id, name="IIBB", rate=Decimal("0.035"))
    s.add_all([rule, charge])
    s.flush()
    return {
        "rule_id": rule.id,
        "charge_id": charge.id,
        "client_id": client.id,
        "category_id": category.id,
        "unit_id": unit_id,
        "supplier_id": supplier.id,
        "other_supplier_id": other_supplier.id,
        "product_category_id": product_category.id,
        "product_id": product.id,
        "offer_id": offer.id,
    }


PARAM_FACTORIES: dict[str, Callable[[OrgWorld], UUID]] = {
    "membership_id": lambda w: w.target.membership_id,
    "invitation_id": lambda w: w.invitation_id,
    "client_id": lambda w: w.ids["client_id"],
    "category_id": lambda w: w.ids["category_id"],
    "supplier_id": lambda w: w.ids["supplier_id"],
    "product_id": lambda w: w.ids["product_id"],
    "offer_id": lambda w: w.ids["offer_id"],
    "rule_id": lambda w: w.ids["rule_id"],
    "charge_id": lambda w: w.ids["charge_id"],
}

Body = dict[str, Any] | Callable[[OrgWorld], dict[str, Any]]

SAMPLE_BODIES: dict[tuple[str, str], Body] = {
    ("PATCH", "/api/v1/organization"): {"name": "Nuevo nombre"},
    ("PATCH", "/api/v1/organization/fiscal"): {"legal_name": "Productora SA"},
    ("PATCH", "/api/v1/members/{membership_id}"): {"role": "QUOTER"},
    ("POST", "/api/v1/invitations"): {"email": "nuevo@example.com", "role": "QUOTER"},
    ("POST", "/api/v1/clients"): {"name": "Cliente nuevo"},
    ("PATCH", "/api/v1/clients/{client_id}"): {"notes": "Paga a 30 días"},
    ("POST", "/api/v1/categories"): {"name": "Categoría nueva"},
    ("PATCH", "/api/v1/categories/{category_id}"): {"sort": 5},
    ("POST", "/api/v1/suppliers"): {"name": "Proveedor nuevo"},
    ("PATCH", "/api/v1/suppliers/{supplier_id}"): {"rating": 4},
    ("POST", "/api/v1/products"): lambda w: {
        "name": "Producto nuevo",
        "category_id": str(w.ids["product_category_id"]),
        "unit_id": str(w.ids["unit_id"]),
    },
    ("PATCH", "/api/v1/products/{product_id}"): {"description_client": "Para el cliente"},
    ("POST", "/api/v1/products/{product_id}/offers"): lambda w: {
        "supplier_id": str(w.ids["other_supplier_id"])
    },
    ("PATCH", "/api/v1/offers/{offer_id}"): {"notes": "Pedir con 48 h"},
    ("POST", "/api/v1/offers/{offer_id}/prices"): {"amount": "1500.50"},
    ("PATCH", "/api/v1/pricing/settings"): {"min_margin": "0.15"},
    ("PUT", "/api/v1/pricing/markup-rules"): lambda w: {
        "scope": "PRODUCT",
        "scope_id": str(w.ids["product_id"]),
        "value": "0.5",
    },
    ("POST", "/api/v1/pricing/sale-charges"): {"name": "Imp. débitos y créditos", "rate": "0.012"},
    ("PATCH", "/api/v1/pricing/sale-charges/{charge_id}"): {"rate": "0.03"},
    ("POST", "/api/v1/pricing/fx-rates"): {"rate": "1450.50"},
}

# Query params obligatorios (con IDs del mundo que se usa).
SAMPLE_QUERIES: dict[tuple[str, str], Callable[[OrgWorld], dict[str, str]]] = {
    ("GET", "/api/v1/pricing/resolve"): lambda w: {
        "product_id": str(w.ids["product_id"]),
        "client_id": str(w.ids["client_id"]),
    },
}


@dataclass(frozen=True)
class RouteInfo:
    method: str
    path: str
    access: str
    permission: Permission | None
    params: tuple[str, ...] = field(default=())

    @property
    def id(self) -> str:
        return f"{self.method} {self.path}"


def _access_markers(dependant: Dependant) -> Iterator[tuple[str, Permission | None]]:
    call = dependant.call
    if call is not None and hasattr(call, ACCESS_MARKER):
        yield getattr(call, ACCESS_MARKER), getattr(call, "__permission__", None)
    for sub in dependant.dependencies:
        yield from _access_markers(sub)


def _flatten(routes: list[BaseRoute], prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    """Rutas efectivas. Desde FastAPI 0.142, ``include_router`` anida los routers en vez de
    copiar sus rutas, así que hay que recorrerlos."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        original = getattr(route, "original_router", None)
        if original is not None:
            context = route.include_context  # type: ignore[attr-defined]
            # Dependencias agregadas al incluir el router no se ven en route.dependant: si
            # alguien las usa, este harness tiene que aprender a leerlas.
            assert not context.dependencies, "include_router(dependencies=...) no soportado"
            yield from _flatten(original.routes, prefix + context.prefix)


def api_routes(app: FastAPI | None = None) -> list[RouteInfo]:
    app = app or create_app()
    routes: list[RouteInfo] = []
    for full_path, route in _flatten(app.routes):
        if not full_path.startswith("/api/"):
            continue
        markers = list(_access_markers(route.dependant))
        for method in sorted(route.methods):
            access = ",".join(sorted({m[0] for m in markers})) or "none"
            permission = next((p for _, p in markers if p is not None), None)
            params = tuple(re.findall(r"{(\w+)}", full_path))
            routes.append(RouteInfo(method, full_path, access, permission, params))
    return routes


def permission_routes() -> list[RouteInfo]:
    return [r for r in api_routes() if r.access == "permission"]


def resolve_path(route: RouteInfo, world: OrgWorld) -> str:
    path = route.path
    for param in route.params:
        factory = PARAM_FACTORIES.get(param)
        assert factory, f"Registrá el parámetro '{param}' en PARAM_FACTORIES ({route.id})"
        path = path.replace("{" + param + "}", str(factory(world)))
    return path


def call(client: TestClient, route: RouteInfo, world: OrgWorld) -> Any:
    """Llama la ruta con los IDs y el body de ``world`` (de otra organización, para aislamiento)."""
    path = resolve_path(route, world)
    sample = SAMPLE_BODIES.get((route.method, route.path))
    body = sample(world) if callable(sample) else sample
    if route.method in {"POST", "PUT", "PATCH"}:
        assert body is not None, f"Registrá un body de ejemplo en SAMPLE_BODIES ({route.id})"
    query = SAMPLE_QUERIES.get((route.method, route.path))
    return client.request(route.method, path, json=body, params=query(world) if query else None)


def logged_in(member: Member) -> TestClient:
    client = TestClient(create_app(), headers={"X-Requested-With": "fetch"})
    response = client.post(
        "/api/v1/auth/login", json={"email": member.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client
