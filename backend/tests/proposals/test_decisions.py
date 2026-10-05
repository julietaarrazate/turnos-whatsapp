"""Aceptar, rechazar y aprobar con OC (P-05, P-06, DOMAIN_MODEL §3.3)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.modules.notifications import console_backend
from tests.conftest import make_client
from tests.proposals.test_proposals import Json, _ok, _send
from tests.security.harness import OrgWorld, build_org, logged_in

BROWSER = {"User-Agent": "Mozilla/5.0 (iPhone) Safari"}


def _token(created: Json) -> str:
    return str(created["public_path"]).removeprefix("/p/")


def _view(created: Json) -> Json:
    return _ok(make_client().get(f"/api/v1/public/proposals/{_token(created)}", headers=BROWSER))


def _decide(created: Json, action: str, **body: Any) -> Any:
    payload = {"content_hash": created["proposal"]["content_hash"], **body}
    return make_client().post(
        f"/api/v1/public/proposals/{_token(created)}/{action}", json=payload, headers=BROWSER
    )


def _event(client: TestClient, world: OrgWorld) -> Json:
    return _ok(client.get(f"/api/v1/events/{world.ids['event_id']}"))


def _listed(client: TestClient, world: OrgWorld) -> list[Json]:
    response = client.get(f"/api/v1/budgets/{world.ids['budget_id']}/proposals")
    assert response.status_code == 200, response.text
    return list(response.json())


def test_client_accepts_online_with_evidence_and_event_is_approved() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    created = _send(owner, world)
    _view(created)
    console_backend.sent.clear()

    stale = _decide(created, "accept", name="Ana", email="ana@x.com", content_hash="0" * 64)
    assert stale.status_code == 409
    assert stale.json()["code"] == "proposal_changed"
    assert _decide(created, "accept", name="", email="ana@x.com").status_code == 422

    accepted = _ok(
        _decide(created, "accept", name=" Ana Pérez ", email="ANA@Cliente.com", comment="Dale")
    )
    assert (accepted["status"], accepted["can_decide"]) == ("ACCEPTED", False)
    assert accepted["decision"]["decided_by_name"] == "Ana Pérez"
    assert accepted["decision"]["method"] == "ONLINE"

    # Idempotente: el doble click o el reintento no cambian nada.
    again = _ok(_decide(created, "accept", name="Otra", email="otra@x.com"))
    assert again["decision"] == accepted["decision"]
    conflict = _decide(created, "reject", reason="No")
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "proposal_already_decided"

    [proposal] = [p for p in _listed(owner, world) if p["id"] == created["proposal"]["id"]]
    assert proposal["decided_by_email"] == "ana@cliente.com"
    assert (proposal["approval_method"], proposal["decision_comment"]) == ("ONLINE", "Dale")
    budget = _ok(owner.get(f"/api/v1/budgets/{world.ids['budget_id']}"))
    event = _event(owner, world)
    assert event["status"] == "APPROVED"
    assert event["accepted_budget_version_id"] == budget["version"]["id"]
    budgets = owner.get("/api/v1/budgets", params={"event_id": str(world.ids["event_id"])})
    approved = {b["id"]: b["approved_version_no"] for b in _ok(budgets)["items"]}
    assert approved == {str(world.ids["budget_id"]): 1, str(world.ids["sent_budget_id"]): None}

    with session_scope(DbContext(organization_id=world.organization_id)) as s:
        ip, ua = s.execute(
            text("SELECT decision_ip, decision_user_agent FROM proposals WHERE id = :id"),
            {"id": created["proposal"]["id"]},
        ).one()
    assert ua == BROWSER["User-Agent"]
    assert ip is not None

    # Un solo aviso (al OWNER), aunque el cliente haya aceptado dos veces.
    assert [m.to for m in console_backend.sent] == [world.members[Role.OWNER].email]
    assert "aceptó" in console_backend.sent[0].subject
    audit = _ok(owner.get("/api/v1/audit-logs"))["items"]
    actions = {(e["action"], e["actor_type"]) for e in audit}
    assert ("proposal.accepted", "PUBLIC_TOKEN") in actions


def test_client_rejects_with_reason_and_event_stays_open() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    created = _send(owner, world)
    assert _decide(created, "reject", reason="").status_code == 422

    rejected = _ok(_decide(created, "reject", reason="Se pasa del presupuesto"))
    assert (rejected["status"], rejected["decision"]["status"]) == ("REJECTED", "REJECTED")
    assert _ok(_decide(created, "reject", reason="Igual"))["status"] == "REJECTED"
    assert _decide(created, "accept", name="Ana", email="a@x.com").status_code == 409

    # Un rechazo no marca el evento como perdido (§3.1): se puede mandar otra versión.
    assert _event(owner, world)["status"] == "NEGOTIATION"
    [listed] = [p for p in _listed(owner, world) if p["id"] == created["proposal"]["id"]]
    assert listed["decision_comment"] == "Se pasa del presupuesto"
    assert any("rechazó" in m.subject for m in console_backend.sent)


def test_expired_superseded_and_closed_events_cannot_be_decided_online() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    first = _send(owner, world)
    owner.post(f"/api/v1/budgets/{world.ids['budget_id']}/versions", json={})
    second = _send(owner, world)
    superseded = _decide(first, "accept", name="Ana", email="a@x.com")
    assert superseded.json()["code"] == "proposal_superseded"

    with session_scope(DbContext(organization_id=world.organization_id)) as s:
        s.execute(
            text("UPDATE proposals SET valid_until = current_date - 1 WHERE id = :id"),
            {"id": second["proposal"]["id"]},
        )
    expired = _decide(second, "accept", name="Ana", email="a@x.com")
    assert (expired.status_code, expired.json()["code"]) == (409, "proposal_expired")

    manager = logged_in(world.members[Role.MANAGER])
    owner.post(f"/api/v1/budgets/{world.ids['budget_id']}/versions", json={})
    third = _send(owner, world)
    lost = manager.post(
        f"/api/v1/events/{world.ids['event_id']}/status",
        json={"to_status": "LOST", "reason": "Eligió otra"},
    )
    assert lost.status_code == 200, lost.text
    assert _view(third)["can_decide"] is False
    closed = _decide(third, "accept", name="Ana", email="a@x.com")
    assert (closed.status_code, closed.json()["code"]) == (409, "event_not_open")


def test_manual_approval_with_po_and_additionals_change_the_baseline() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    quoter = logged_in(world.members[Role.QUOTER])
    manager = logged_in(world.members[Role.MANAGER])
    first = _send(owner, world)
    path = f"/api/v1/proposals/{first['proposal']['id']}/approve"
    assert quoter.post(path, json={"po_number": "OC-1"}).status_code == 403

    # Venció, pero la OC llegó: la productora la puede aprobar igual.
    with session_scope(DbContext(organization_id=world.organization_id)) as s:
        s.execute(
            text("UPDATE proposals SET valid_until = current_date - 1 WHERE id = :id"),
            {"id": first["proposal"]["id"]},
        )
    approved = _ok(manager.post(path, json={"po_number": " OC-4471 ", "comment": "Por mail"}))
    assert (approved["status"], approved["approval_method"]) == ("ACCEPTED", "MANUAL")
    assert approved["po_number"] == "OC-4471"
    assert manager.post(path, json={}).json()["code"] == "proposal_already_decided"
    event = _event(owner, world)
    v1 = event["accepted_budget_version_id"]
    assert event["status"] == "APPROVED"
    assert _view(first)["decision"]["method"] == "MANUAL"

    # Adicionales: nueva versión, propuesta y aprobación manual. El cliente ya no decide online.
    owner.post(f"/api/v1/budgets/{world.ids['budget_id']}/versions", json={})
    second = _send(owner, world)
    assert _view(second)["can_decide"] is False
    assert _decide(second, "accept", name="Ana", email="a@x.com").status_code == 409
    _ok(manager.post(f"/api/v1/proposals/{second['proposal']['id']}/approve", json={}))
    event = _event(owner, world)
    assert event["status"] == "APPROVED"
    assert event["accepted_budget_version_id"] not in {None, v1}
    assert [h["to_status"] for h in event["history"]].count("APPROVED") == 1


def test_first_view_notifies_once_and_bots_do_not() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    created = _send(owner, world)
    console_backend.sent.clear()
    make_client().get(
        f"/api/v1/public/proposals/{_token(created)}", headers={"User-Agent": "WhatsApp/2"}
    )
    assert console_backend.sent == []
    _view(created)
    _view(created)
    assert [m.template for m in console_backend.sent] == ["proposal_viewed"]
