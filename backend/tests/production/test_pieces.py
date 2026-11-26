"""Piezas a medida del evento: alta, fases de fabricación, avance y auditoría."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from app.modules.catalog import today_ar
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in


def _pieces(client: TestClient, world: OrgWorld) -> dict[str, Any]:
    return dict(_ok(client.get(f"/api/v1/events/{world.ids['event_id']}/pieces")))


def _add(client: TestClient, world: OrgWorld, **body: Any) -> dict[str, Any]:
    response = client.post(f"/api/v1/events/{world.ids['event_id']}/pieces", json=body)
    return dict(_ok(response, 201))


def test_pieces_progress_follows_the_fabrication_phases() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    # El harness trae una pieza de ejemplo en diseño (0 %).
    start = _pieces(production, world)
    assert (start["total"], start["ready"], start["progress"]) == (1, 0, 0)

    mostrador = _add(production, world, name="  Mostrador recepción ", area="CARPENTRY")
    assert mostrador["name"] == "Mostrador recepción"
    assert (mostrador["area"], mostrador["status"]) == ("CARPENTRY", "DESIGN")
    tarima = _add(production, world, name="Tarima principal", area="CARPENTRY")

    def phase(piece: dict[str, Any], status: str) -> dict[str, Any]:
        return dict(_ok(production.patch(f"/api/v1/pieces/{piece['id']}", json={"status": status})))

    assert phase(mostrador, "IN_WORKSHOP")["status_changed_at"] is not None
    phase(tarima, "MOUNTED")
    # Diseño 0, taller 50, montado 100 → 50 %; listas: solo la montada.
    board = _pieces(production, world)
    assert (board["total"], board["ready"], board["progress"]) == (3, 1, 50)
    assert [p["name"] for p in board["pieces"]] == [
        "Pieza ejemplo",
        "Mostrador recepción",
        "Tarima principal",
    ]

    # Se puede volver atrás (un plano rechazado vuelve a diseño).
    assert phase(mostrador, "DESIGN")["status"] == "DESIGN"

    owner = logged_in(world.members[Role.OWNER])
    actions = [e["action"] for e in _ok(owner.get("/api/v1/audit-logs"))["items"]]
    assert actions.count("piece.status_changed") == 3
    assert actions.count("piece.created") == 2


def test_late_assignee_and_delete() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    production = world.members[Role.PRODUCTION]
    yesterday = (today_ar() - timedelta(days=1)).isoformat()
    piece = _add(
        owner,
        world,
        name="Corpóreo LED",
        area="GRAPHICS",
        due_date=yesterday,
        assignee_user_id=str(production.user_id),
        notes="Letras de 40 cm",
    )
    assert piece["late"] is True  # vencida y sin terminar
    assert piece["assignee_name"]
    ready = _ok(owner.patch(f"/api/v1/pieces/{piece['id']}", json={"status": "READY"}))
    assert ready["late"] is False  # lista para carga: ya no está atrasada

    # El responsable tiene que ser de la organización.
    other = build_org("b")
    stranger = str(other.members[Role.OWNER].user_id)
    bad = owner.patch(f"/api/v1/pieces/{piece['id']}", json={"assignee_user_id": stranger})
    assert bad.status_code == 422

    assert owner.delete(f"/api/v1/pieces/{piece['id']}").status_code == 204
    assert all(p["id"] != piece["id"] for p in _pieces(owner, world)["pieces"])


def test_closed_event_pieces_are_read_only() -> None:
    world = build_org("a")
    _approved(world)
    manager = logged_in(world.members[Role.MANAGER])
    base = f"/api/v1/events/{world.ids['event_id']}"
    _ok(manager.post(f"{base}/start-production"))
    _ok(manager.post(f"{base}/complete"))
    _ok(manager.post(f"{base}/close"))
    blocked = manager.patch(f"/api/v1/pieces/{world.ids['piece_id']}", json={"status": "MOUNTED"})
    assert (blocked.status_code, blocked.json()["code"]) == (409, "event_locked")
    assert manager.post(f"{base}/pieces", json={"name": "Otra"}).status_code == 409
    assert _pieces(manager, world)["total"] == 1  # se sigue viendo
