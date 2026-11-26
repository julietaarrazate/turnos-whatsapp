"""Actividad: movimientos de producción, lo más nuevo primero, sin datos de otra organización."""

from base64 import b64encode

from app.core.enums import Role
from tests.proposals.test_proposals import _ok
from tests.security.harness import build_org, logged_in


def test_feed_shows_production_moves_newest_first() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]
    event_id = world.ids["event_id"]

    _ok(production.patch(f"/api/v1/pieces/{piece_id}", json={"status": "IN_WORKSHOP"}))
    update = _ok(
        production.post(f"/api/v1/pieces/{piece_id}/updates", json={"note": "Letras cortadas"}), 201
    )
    plan = {
        "title": "Plano de corte",
        "filename": "p.pdf",
        "file_base64": b64encode(b"%PDF-1.4 x").decode(),
    }
    _ok(production.post(f"/api/v1/pieces/{piece_id}/plans", json=plan), 201)

    # Otra organización con movimientos: no aparecen.
    other = build_org("b")
    other_prod = logged_in(other.members[Role.PRODUCTION])
    _ok(other_prod.patch(f"/api/v1/pieces/{other.ids['piece_id']}", json={"status": "MOUNTED"}))

    viewer = logged_in(world.members[Role.VIEWER])
    page = _ok(viewer.get("/api/v1/activity"))
    kinds = [item["kind"] for item in page["items"]]
    assert kinds[:3] == ["piece.plan_uploaded", "piece.update_posted", "piece.status_changed"]
    assert all(item["event"]["id"] == str(event_id) for item in page["items"])
    plan_item, update_item, status_item = page["items"][:3]
    assert (plan_item["title"], plan_item["version"], plan_item["piece"]) == (
        "Plano de corte",
        1,
        "Pieza ejemplo",
    )
    assert (update_item["note"], update_item["update_id"], update_item["has_photo"]) == (
        "Letras cortadas",
        update["id"],
        False,
    )
    assert (status_item["status"], status_item["actor_name"]) == (
        "IN_WORKSHOP",
        update["author_name"],
    )
    assert page["next_before"] is None

    # Filtrar por evento y pedir anteriores.
    assert _ok(viewer.get("/api/v1/activity", params={"event_id": str(event_id)}))["items"]
    older = _ok(viewer.get("/api/v1/activity", params={"before": status_item["created_at"]}))
    assert all(i["created_at"] < status_item["created_at"] for i in older["items"])

    # El taller tiene su lista (Mis tareas), no la actividad de toda la productora.
    crew = logged_in(world.members[Role.CREW])
    assert crew.get("/api/v1/activity").status_code == 403


def test_bell_counts_moves_of_others_until_activity_is_opened() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    production = logged_in(world.members[Role.PRODUCTION])
    piece_id = world.ids["piece_id"]

    # Lo propio no avisa; lo de otros sí.
    _ok(owner.patch(f"/api/v1/pieces/{piece_id}", json={"status": "TO_BUY"}))
    assert _ok(owner.get("/api/v1/activity/unread"))["count"] == 0
    _ok(production.patch(f"/api/v1/pieces/{piece_id}", json={"status": "IN_WORKSHOP"}))
    _ok(production.post(f"/api/v1/pieces/{piece_id}/updates", json={"note": "Ya en taller"}), 201)
    bell = _ok(owner.get("/api/v1/activity/unread"))
    assert (bell["count"], bell["seen_at"]) == (2, None)

    # Abrir Actividad apaga la campanita de quien la abre, no la de los demás.
    seen = _ok(owner.post("/api/v1/activity/seen", json={}))
    assert (seen["count"], seen["seen_at"] is not None) == (0, True)
    assert _ok(owner.get("/api/v1/activity/unread"))["count"] == 0
    assert _ok(production.get("/api/v1/activity/unread"))["count"] == 1  # el TO_BUY del dueño

    _ok(production.patch(f"/api/v1/pieces/{piece_id}", json={"status": "READY"}))
    again = _ok(owner.get("/api/v1/activity/unread"))
    assert again["count"] == 1
    assert again["seen_at"] is not None
    # Marcar dos veces no duplica nada.
    _ok(owner.post("/api/v1/activity/seen", json={}))
    _ok(owner.post("/api/v1/activity/seen", json={}))
    assert _ok(owner.get("/api/v1/activity/unread"))["count"] == 0

    crew = logged_in(world.members[Role.CREW])
    assert crew.get("/api/v1/activity/unread").status_code == 403
