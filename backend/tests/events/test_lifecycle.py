"""Ciclo de producción del evento (DOMAIN_MODEL §3.1, O-01)."""

from app.core.enums import Role
from tests.proposals.test_decisions import _decide
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import build_org, logged_in


def test_production_lifecycle_with_permissions_and_history() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    production = logged_in(world.members[Role.PRODUCTION])
    manager = logged_in(world.members[Role.MANAGER])
    base = f"/api/v1/events/{world.ids['event_id']}"

    # Sin aprobar no se puede producir.
    early = production.post(f"{base}/start-production")
    assert (early.status_code, early.json()["code"]) == (409, "event_transition_invalid")

    _ok(_decide(_send(owner, world), "accept", name="Ana", email="ana@x.com"))
    assert production.post(f"{base}/complete").status_code == 409  # todavía no arrancó

    started = _ok(production.post(f"{base}/start-production"))
    assert started["started"] is True
    assert _ok(production.get(base))["status"] == "IN_PRODUCTION"
    done = _ok(production.post(f"{base}/complete"))
    assert done["status"] == "COMPLETED"

    # El cierre financiero es de MANAGER+.
    assert production.post(f"{base}/close").status_code == 403
    assert _ok(manager.post(f"{base}/close"))["status"] == "CLOSED"
    assert manager.post(f"{base}/reopen", json={"reason": ""}).status_code == 422
    reopened = _ok(manager.post(f"{base}/reopen", json={"reason": "Faltaba una factura"}))
    assert reopened["status"] == "COMPLETED"

    history = [(h["to_status"], h["reason"]) for h in reopened["history"]]
    assert history[-5:] == [
        ("APPROVED", None),
        ("IN_PRODUCTION", None),
        ("COMPLETED", None),
        ("CLOSED", None),
        ("COMPLETED", "Faltaba una factura"),
    ]
    # Ya realizado, no se puede perder ni cancelar.
    lost = manager.post(f"{base}/status", json={"to_status": "LOST", "reason": "x"})
    assert lost.status_code == 409
