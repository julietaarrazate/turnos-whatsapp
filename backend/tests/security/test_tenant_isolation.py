"""Caso obligatorio 5 del brief: un usuario de la organización A no accede a nada de B.

Recorre TODAS las rutas con parámetros: con IDs de B, un OWNER de A recibe 404 (no 403:
no se revela que el recurso existe).
"""

import pytest

from app.core.enums import Role
from tests.security.harness import (
    RouteInfo,
    build_org,
    call,
    logged_in,
    permission_routes,
    resolve_path,
)

ROUTES_WITH_IDS = [r for r in permission_routes() if r.params]


def test_there_are_routes_with_ids_to_check() -> None:
    assert ROUTES_WITH_IDS


@pytest.mark.parametrize("route", ROUTES_WITH_IDS, ids=[r.id for r in ROUTES_WITH_IDS])
def test_ids_of_another_org_return_404(route: RouteInfo) -> None:
    org_a = build_org("a")
    org_b = build_org("b")
    client = logged_in(org_a.members[Role.OWNER])
    response = call(client, route, resolve_path(route, org_b))
    assert response.status_code == 404, response.text


def test_lists_only_show_own_org() -> None:
    org_a = build_org("a")
    org_b = build_org("b")
    client = logged_in(org_a.members[Role.OWNER])
    # Generar actividad auditada en B.
    logged_in(org_b.members[Role.OWNER]).patch("/api/v1/organization", json={"name": "B2"})

    members = client.get("/api/v1/members").json()
    assert {m["user_id"] for m in members} == {
        str(m.user_id) for m in [*org_a.members.values(), org_a.target]
    }
    invitations = client.get("/api/v1/invitations").json()
    assert [i["id"] for i in invitations] == [str(org_a.invitation_id)]
    audit = client.get("/api/v1/audit-logs").json()["items"]
    assert all(e["action"] != "org.settings_changed" for e in audit)
    assert client.get("/api/v1/organization").json()["id"] == str(org_a.organization_id)
