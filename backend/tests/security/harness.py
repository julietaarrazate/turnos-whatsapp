"""Infraestructura de los tests de seguridad que recorren TODAS las rutas de la API.

Cuando un módulo nuevo agrega una ruta con parámetros o con body, estos tests fallan hasta
que se registre acá cómo obtener un ID válido (``PARAM_FACTORIES``) y un body de ejemplo
(``SAMPLE_BODIES``). Así ninguna ruta nueva queda fuera de la verificación.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import BaseRoute

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.core.permissions import Permission
from app.main import create_app
from app.modules.auth import create_invitation
from app.modules.auth.dependencies import ACCESS_MARKER
from tests.factories import DEFAULT_PASSWORD, Member, add_member, create_org, create_user


@dataclass
class OrgWorld:
    organization_id: UUID
    members: dict[Role, Member]
    target: Member  # un miembro extra sobre el que se actúa (cambiar rol, desactivar)
    invitation_id: UUID


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
    return OrgWorld(org_id, members, target, invitation_id)


PARAM_FACTORIES: dict[str, Callable[[OrgWorld], UUID]] = {
    "membership_id": lambda w: w.target.membership_id,
    "invitation_id": lambda w: w.invitation_id,
}

SAMPLE_BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("PATCH", "/api/v1/organization"): {"name": "Nuevo nombre"},
    ("PATCH", "/api/v1/organization/fiscal"): {"legal_name": "Productora SA"},
    ("PATCH", "/api/v1/members/{membership_id}"): {"role": "QUOTER"},
    ("POST", "/api/v1/invitations"): {"email": "nuevo@example.com", "role": "QUOTER"},
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


def call(client: TestClient, route: RouteInfo, path: str) -> Any:
    body = SAMPLE_BODIES.get((route.method, route.path))
    if route.method in {"POST", "PUT", "PATCH"}:
        assert body is not None, f"Registrá un body de ejemplo en SAMPLE_BODIES ({route.id})"
    return client.request(route.method, path, json=body)


def logged_in(member: Member) -> TestClient:
    client = TestClient(create_app(), headers={"X-Requested-With": "fetch"})
    response = client.post(
        "/api/v1/auth/login", json={"email": member.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client
