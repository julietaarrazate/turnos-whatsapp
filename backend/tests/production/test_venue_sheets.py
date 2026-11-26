"""Ficha del lugar: se carga en un evento y el próximo evento en el mismo lugar ya la tiene."""

from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import Role
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in


def _venue(client: TestClient, world: OrgWorld, venue: str | None) -> None:
    _ok(client.patch(f"/api/v1/events/{world.ids['event_id']}", json={"venue": venue}))


def _sheet(client: TestClient, event_id: Any) -> dict[str, Any]:
    return dict(_ok(client.get(f"/api/v1/events/{event_id}/venue-sheet")))


def _new_event(client: TestClient, venue: str) -> str:
    event = _ok(
        client.post(
            "/api/v1/events",
            json={"client_name": "Otro cliente", "name": "Expo 2027", "venue": venue},
        ),
        201,
    )
    return str(event["id"])


def test_sheet_is_shared_by_every_event_in_the_same_venue() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    _venue(owner, world, "Costa Salguero")
    empty = _sheet(owner, world.ids["event_id"])
    assert (empty["venue"], empty["sheet"], empty["can_edit"]) == ("Costa Salguero", None, True)

    production = logged_in(world.members[Role.PRODUCTION])
    saved = _ok(
        production.put(
            f"/api/v1/events/{world.ids['event_id']}/venue-sheet",
            json={
                "load_in": "  Carga por Sarmiento de 7 a 10  ",
                "measures": "Puerta 3,20 m de alto",
                "maps_url": "https://maps.app.goo.gl/abc",
                "notes": "   ",
            },
        )
    )
    sheet = saved["sheet"]
    assert sheet["load_in"] == "Carga por Sarmiento de 7 a 10"
    assert sheet["notes"] is None
    assert sheet["updated_by_name"]

    # Otro evento en el mismo lugar (escrito distinto) ya ve la ficha.
    other = _new_event(owner, "costa salguero ")
    reused = _sheet(owner, other)
    assert reused["sheet"]["measures"] == "Puerta 3,20 m de alto"
    assert reused["other_events"] == 1


def test_who_can_edit_and_what_is_checked() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    base = f"/api/v1/events/{world.ids['event_id']}/venue-sheet"
    _venue(owner, world, None)
    missing = owner.put(base, json={"load_in": "x"})
    assert (missing.status_code, missing.json()["code"]) == (422, "venue_missing")
    _venue(owner, world, "La Rural")
    bad = owner.put(base, json={"maps_url": "http://maps.com"})
    assert (bad.status_code, bad.json()["code"]) == (422, "url_invalid")

    viewer = logged_in(world.members[Role.VIEWER])
    assert _sheet(viewer, world.ids["event_id"])["can_edit"] is False
    denied = viewer.put(base, json={"load_in": "x"})
    assert (denied.status_code, denied.json()["code"]) == (403, "files_read_only")

    stranger = logged_in(build_org("b").members[Role.OWNER])
    assert stranger.get(base).status_code == 404
