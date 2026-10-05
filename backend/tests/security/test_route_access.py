"""Toda ruta de la API declara su nivel de acceso (ARCHITECTURE §8.2)."""

from app.core.enums import Role
from app.core.permissions import ROLE_PERMISSIONS, Permission
from tests.security.harness import api_routes

PUBLIC_ROUTES = {
    "POST /api/v1/auth/login",
    "POST /api/v1/auth/refresh",
    "POST /api/v1/auth/logout",
    "POST /api/v1/auth/password-reset",
    "POST /api/v1/auth/password-reset/confirm",
    "GET /api/v1/auth/invitations/{token}",
    "POST /api/v1/auth/invitations/accept",
    # Propuesta pública: solo con el token, lista blanca del snapshot (ARCHITECTURE §8.4).
    "GET /api/v1/public/proposals/{token}",
    # Aceptar / rechazar: solo con el token, hash del contenido visto y rate limit por IP.
    "POST /api/v1/public/proposals/{token}/accept",
    "POST /api/v1/public/proposals/{token}/reject",
}


def test_every_route_declares_exactly_one_access_level() -> None:
    routes = api_routes()
    assert routes
    for route in routes:
        assert route.access in {"public", "authenticated", "permission"}, (
            f"{route.id} declara acceso '{route.access}': usá Public, CurrentAuth o require()"
        )


def test_public_routes_are_exactly_the_reviewed_list() -> None:
    public = {r.id for r in api_routes() if r.access == "public"}
    assert public == PUBLIC_ROUTES, (
        "Una ruta pública nueva tiene que revisarse y agregarse a PUBLIC_ROUTES"
    )


def test_every_permission_is_granted_to_owner() -> None:
    assert set(Permission) == set(ROLE_PERMISSIONS[Role.OWNER])
