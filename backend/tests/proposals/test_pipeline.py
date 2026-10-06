"""Pipeline de presupuestos (B-12) y "para seguir" (PRODUCT_SPEC §8)."""

from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.core.security import utcnow
from app.modules.catalog import today_ar
from tests.proposals.test_decisions import _decide, _view
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import OrgWorld, build_org, logged_in


def _pipeline(client: TestClient, **params: Any) -> dict[str, Any]:
    return _ok(client.get("/api/v1/pipeline", params=params))


def _item(data: dict[str, Any], budget_id: object) -> dict[str, Any]:
    return next(i for i in data["items"] if i["id"] == str(budget_id))


def _age(world: OrgWorld, proposal_id: str, **changes: object) -> None:
    """Corre en el tiempo una propuesta (sent_at, first_viewed_at, valid_until)."""
    assignments = ", ".join(f"{column} = :{column}" for column in changes)
    with session_scope(DbContext(organization_id=world.organization_id)) as s:
        s.execute(
            text(f"UPDATE proposals SET {assignments} WHERE id = :id"),  # noqa: S608 — columnas fijas del test
            {**changes, "id": proposal_id},
        )


def _ago(**delta: float) -> datetime:
    return utcnow() - timedelta(**delta)


def test_derived_status_follows_the_proposals() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget_id = world.ids["budget_id"]
    data = _pipeline(owner)
    assert _item(data, budget_id)["pipeline_status"] == "DRAFT"
    # El harness ya envió el otro presupuesto del evento.
    assert _item(data, world.ids["sent_budget_id"])["pipeline_status"] == "SENT"

    first = _send(owner, world)
    assert _item(_pipeline(owner), budget_id)["pipeline_status"] == "SENT"
    _view(first)
    item = _item(_pipeline(owner), budget_id)
    assert (item["pipeline_status"], item["proposals_sent"]) == ("VIEWED", 1)
    assert item["last_proposal"]["view_count"] == 1

    owner.post(f"/api/v1/budgets/{budget_id}/versions", json={})
    second = _send(owner, world)
    assert _item(_pipeline(owner), budget_id)["pipeline_status"] == "NEGOTIATION"

    _ok(_decide(second, "accept", name="Ana", email="ana@x.com"))
    data = _pipeline(owner, status="ACCEPTED")
    assert [i["id"] for i in data["items"]] == [str(budget_id)]
    assert data["counts"]["ACCEPTED"] == 1


def test_lost_event_and_filters() -> None:
    world = build_org("a")
    manager = logged_in(world.members[Role.MANAGER])
    manager.post(
        f"/api/v1/events/{world.ids['event_id']}/status",
        json={"to_status": "LOST", "reason": "Eligió otra"},
    )
    data = _pipeline(manager)
    assert {i["pipeline_status"] for i in data["items"]} == {"LOST"}
    assert data["counts"]["LOST"] == 2
    assert _pipeline(manager, q="no-existe")["items"] == []
    viewer = logged_in(world.members[Role.VIEWER])
    assert viewer.get("/api/v1/pipeline").status_code == 200


def test_follow_up_reasons() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    budget_id = world.ids["budget_id"]
    created = _send(owner, world, valid_days=30)
    proposal_id = created["proposal"]["id"]
    assert _item(_pipeline(owner), budget_id)["follow_up"] is None

    # Enviada hace más de 5 días (el umbral por defecto) y sin abrir.
    _age(world, proposal_id, sent_at=_ago(days=6))
    item = _item(_pipeline(owner), budget_id)
    assert item["follow_up"] == "NO_RESPONSE"
    data = _pipeline(owner, follow_up=True)
    assert data["follow_up_days"] == 5
    assert str(budget_id) in [i["id"] for i in data["items"]]

    # El umbral se configura por organización.
    owner.patch("/api/v1/organization", json={"follow_up_days": 10})
    assert _item(_pipeline(owner), budget_id)["follow_up"] is None

    # Vista hace más de 48 h, sin respuesta.
    _age(world, proposal_id, first_viewed_at=_ago(hours=50))
    assert _item(_pipeline(owner), budget_id)["follow_up"] == "VIEWED_NO_ANSWER"

    # Vence mañana: es lo más urgente.
    _age(world, proposal_id, valid_until=today_ar() + timedelta(days=1))
    assert _item(_pipeline(owner), budget_id)["follow_up"] == "EXPIRING"

    # Ya decidida: no hay nada que seguir.
    _ok(_decide(created, "reject", reason="No"))
    assert _item(_pipeline(owner), budget_id)["follow_up"] is None
