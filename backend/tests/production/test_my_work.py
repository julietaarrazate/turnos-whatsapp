"""Mis tareas: el rol Taller/Montaje ve y mueve solo lo propio, sin presupuestos ni plata."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from app.modules.catalog import today_ar
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in


def _piece(owner: TestClient, world: OrgWorld, **body: Any) -> dict[str, Any]:
    url = f"/api/v1/events/{world.ids['event_id']}/pieces"
    return dict(_ok(owner.post(url, json=body), 201))


def _task(owner: TestClient, world: OrgWorld, **body: Any) -> dict[str, Any]:
    url = f"/api/v1/events/{world.ids['event_id']}/tasks"
    return dict(_ok(owner.post(url, json=body), 201))


def test_crew_sees_and_moves_only_what_is_assigned_to_them() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    crew_member = world.members[Role.CREW]
    crew = logged_in(crew_member)
    me = str(crew_member.user_id)
    other = str(world.members[Role.PRODUCTION].user_id)
    yesterday = (today_ar() - timedelta(days=1)).isoformat()
    next_week = (today_ar() + timedelta(days=7)).isoformat()

    mine = _piece(owner, world, name="Mostrador", area="CARPENTRY", assignee_user_id=me)
    late = _piece(owner, world, name="Tótem", assignee_user_id=me, due_date=yesterday)
    theirs = _piece(owner, world, name="Tarima", assignee_user_id=other)
    _piece(owner, world, name="Ya montada", assignee_user_id=me)
    mounted = _ok(owner.get(f"/api/v1/events/{world.ids['event_id']}/pieces"))["pieces"][-1]
    _ok(owner.patch(f"/api/v1/pieces/{mounted['id']}", json={"status": "MOUNTED"}))
    task = _task(owner, world, title="Cargar camión", assignee_user_id=me, due_date=next_week)
    _task(owner, world, title="Pedir planos", assignee_user_id=other)

    work = _ok(crew.get("/api/v1/my-work"))
    # Lo atrasado primero; lo montado ya no aparece; lo de otra persona tampoco.
    assert [p["name"] for p in work["pieces"]] == ["Tótem", "Mostrador"]
    assert work["pieces"][0]["late"] is True
    assert work["pieces"][1]["event"]["name"] == "Evento ejemplo"
    assert [t["title"] for t in work["tasks"]] == ["Cargar camión"]

    # Mueve lo suyo con un toque, y queda en la auditoría.
    moved = _ok(crew.patch(f"/api/v1/my-work/pieces/{mine['id']}", json={"status": "IN_WORKSHOP"}))
    assert moved["status"] == "IN_WORKSHOP"
    done = _ok(crew.patch(f"/api/v1/my-work/tasks/{task['id']}", json={"status": "DONE"}))
    assert done["status"] == "DONE"
    assert [t["title"] for t in _ok(crew.get("/api/v1/my-work"))["tasks"]] == []
    audit = _ok(owner.get("/api/v1/audit-logs"))["items"]
    assert any(e["action"] == "piece.status_changed" and e["actor_user_id"] == me for e in audit), (
        "el cambio del taller tiene que quedar registrado a su nombre"
    )

    # Lo de otra persona: 404, como si no existiera.
    url = f"/api/v1/my-work/pieces/{theirs['id']}"
    assert crew.patch(url, json={"status": "MOUNTED"}).status_code == 404
    assert late["status"] == "DESIGN"


def test_crew_does_not_see_budgets_clients_or_money() -> None:
    world = build_org("a")
    crew = logged_in(world.members[Role.CREW])
    for path in (
        f"/api/v1/budgets/{world.ids['budget_id']}",
        f"/api/v1/events/{world.ids['event_id']}",
        f"/api/v1/events/{world.ids['event_id']}/pieces",
        "/api/v1/clients",
        "/api/v1/dashboard",
        "/api/v1/organization",
    ):
        response = crew.get(path)
        assert response.status_code == 403, f"{path}: {response.text}"
    me = _ok(crew.get("/api/v1/auth/me"))
    assert me["permissions"] == ["work.own"]


def test_closed_events_leave_my_work_and_cannot_be_moved() -> None:
    world = build_org("a")
    _approved(world)
    manager = logged_in(world.members[Role.MANAGER])
    crew_member = world.members[Role.CREW]
    crew = logged_in(crew_member)
    piece_id = world.ids["piece_id"]
    _ok(
        manager.patch(
            f"/api/v1/pieces/{piece_id}", json={"assignee_user_id": str(crew_member.user_id)}
        )
    )
    assert len(_ok(crew.get("/api/v1/my-work"))["pieces"]) == 1

    base = f"/api/v1/events/{world.ids['event_id']}"
    _ok(manager.post(f"{base}/start-production"))
    _ok(manager.post(f"{base}/complete"))
    _ok(manager.post(f"{base}/close"))
    assert _ok(crew.get("/api/v1/my-work"))["pieces"] == []
    blocked = crew.patch(f"/api/v1/my-work/pieces/{piece_id}", json={"status": "MOUNTED"})
    assert (blocked.status_code, blocked.json()["code"]) == (409, "event_locked")


def test_crew_can_be_invited_and_assigned() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    invited = owner.post(
        "/api/v1/invitations", json={"email": "taller@a.example.com", "role": "CREW"}
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["role"] == "CREW"


def test_open_pieces_to_pick_where_a_photo_goes() -> None:
    world = build_org("a")
    _approved(world)  # el evento del harness pasa a aprobado
    owner = logged_in(world.members[Role.OWNER])
    production_member = world.members[Role.PRODUCTION]
    production = logged_in(production_member)
    me = str(production_member.user_id)
    _piece(owner, world, name="Tarima", assignee_user_id=me)
    mounted = _piece(owner, world, name="Ya montada")
    _ok(owner.patch(f"/api/v1/pieces/{mounted['id']}", json={"status": "MOUNTED"}))

    names = [p["name"] for p in _ok(production.get("/api/v1/pieces/open"))]
    # La propia primero; la montada no aparece.
    assert names[0] == "Tarima"
    assert "Pieza ejemplo" in names
    assert "Ya montada" not in names
    assert _ok(production.get("/api/v1/pieces/open"))[0]["mine"] is True

    # El taller elige entre lo suyo (Mis tareas): esta lista no es para su rol.
    crew = logged_in(world.members[Role.CREW])
    assert crew.get("/api/v1/pieces/open").status_code == 403
