"""Matriz rol × endpoint, generada desde ROLE_PERMISSIONS (la única fuente de verdad)."""

import pytest

from app.core.enums import Role
from app.core.permissions import ROLE_PERMISSIONS, Permission
from tests.security.harness import (
    RouteInfo,
    build_org,
    call,
    logged_in,
    permission_routes,
    resolve_path,
)

CASES = [(route, role) for route in permission_routes() for role in Role]


@pytest.mark.parametrize(
    ("route", "role"), CASES, ids=[f"{r.id} as {role.value}" for r, role in CASES]
)
def test_role_access_matches_matrix(route: RouteInfo, role: Role) -> None:
    world = build_org("a")
    client = logged_in(world.members[role])
    response = call(client, route, resolve_path(route, world))
    assert route.permission is not None
    allowed = route.permission in ROLE_PERMISSIONS[role]
    body = response.json() if response.content else None
    code = body.get("code") if isinstance(body, dict) else None
    if allowed:
        assert code != "permission_denied", f"{role} debería poder: {response.text}"
    else:
        assert response.status_code == 403, response.text
        assert code == "permission_denied"


def test_production_role_never_has_margin_access() -> None:
    assert Permission.MARGIN_VIEW not in ROLE_PERMISSIONS[Role.PRODUCTION]
    assert Permission.COST_VIEW in ROLE_PERMISSIONS[Role.PRODUCTION]
