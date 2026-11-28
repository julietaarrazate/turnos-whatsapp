"""Avisos al teléfono: suscribirse, a quién le llega y qué dice."""

from typing import Any

import pytest
from sqlalchemy import select

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.modules.audit import AuditLog
from app.modules.push import service
from tests.proposals.test_proposals import _ok
from tests.security.harness import OrgWorld, build_org, logged_in

FCM = "https://fcm.googleapis.com/fcm/send/abc"
KEYS = {"p256dh": "B" + "x" * 86, "auth": "y" * 22}


def _subscribe(client: Any, endpoint: str = FCM) -> Any:
    return client.post("/api/v1/push/subscriptions", json={"endpoint": endpoint, "keys": KEYS})


def test_subscribe_status_and_unsubscribe() -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    status = _ok(owner.get("/api/v1/push"))
    assert len(status["public_key"]) == 87  # punto P-256 sin comprimir, base64url
    assert status["devices"] == 0
    # La clave es siempre la misma (se crea una sola vez).
    assert _ok(owner.get("/api/v1/push"))["public_key"] == status["public_key"]

    assert _subscribe(owner).status_code == 204
    assert _subscribe(owner).status_code == 204  # el mismo navegador no se duplica
    assert _ok(owner.get("/api/v1/push"))["devices"] == 1

    # Solo servicios de avisos conocidos: nunca una dirección cualquiera.
    bad = _subscribe(owner, "https://evil.example.com/hook")
    assert (bad.status_code, bad.json()["code"]) == (422, "push_endpoint_invalid")
    assert _subscribe(owner, "http://fcm.googleapis.com/x").status_code == 422

    assert owner.post("/api/v1/push/unsubscribe", json={"endpoint": FCM}).status_code == 204
    assert _ok(owner.get("/api/v1/push"))["devices"] == 0


def _last_log(world: OrgWorld, action: str) -> Any:
    with session_scope(DbContext(organization_id=world.organization_id)) as db:
        return (
            db.execute(
                select(AuditLog.id)
                .where(AuditLog.organization_id == world.organization_id, AuditLog.action == action)
                .order_by(AuditLog.created_at.desc())
            )
            .scalars()
            .first()
        )


def test_others_get_the_notice_but_not_the_author_nor_the_workshop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    crew = logged_in(world.members[Role.CREW])
    production = logged_in(world.members[Role.PRODUCTION])
    _subscribe(owner, FCM + "-owner")
    _subscribe(crew, FCM + "-crew")
    _subscribe(production, FCM + "-production")

    _ok(_post_note(production, world), 201)
    sent: list[tuple[str, service.Message]] = []
    monkeypatch.setattr(
        service, "_send", lambda sub, msg, _pem: sent.append((sub.endpoint, msg)) or True
    )
    service.deliver([(world.organization_id, _last_log(world, "piece.update_posted"))])

    assert [endpoint for endpoint, _ in sent] == [FCM + "-owner"]
    message = sent[0][1]
    assert "dejó una nota en" in message.body
    assert message.url.startswith("/events/")


def _post_note(client: Any, world: OrgWorld) -> Any:
    return client.post(f"/api/v1/pieces/{world.ids['piece_id']}/updates", json={"note": "Listo"})


def test_gone_devices_are_forgotten(monkeypatch: pytest.MonkeyPatch) -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    _subscribe(owner)
    monkeypatch.setattr(service, "_send", lambda *_: False)  # el navegador desinstaló la app
    assert _ok(owner.post("/api/v1/push/test"))["sent"] == 0
    assert _ok(owner.get("/api/v1/push"))["devices"] == 0


def test_messages_read_like_the_activity_feed() -> None:
    def log(action: str, **after: Any) -> AuditLog:
        return AuditLog(action=action, entity_id=None, after=after)

    def body(entry: AuditLog, actor: str | None = "Vale") -> str:
        result = service.message(entry, actor, "Expo", 12)
        assert result is not None
        assert result.title == "#12 Expo"
        return result.body

    assert body(log("piece.status_changed", piece="Mostrador", status="IN_WORKSHOP")) == (
        "Vale pasó Mostrador a En taller"
    )
    assert body(log("piece.update_posted", piece="Mostrador", photo=True)) == (
        "Vale dejó una foto de avance en Mostrador"
    )
    assert body(
        log("file.approval_decided", title="Render", status="APPROVED", by="Laura"), None
    ) == ("✓ Laura aprobó Render")
    assert (
        body(
            log("file.approval_decided", title="Render", status="CHANGES", by="Laura", note="Logo"),
            None,
        )
        == "Laura pidió cambios en Render: “Logo”"
    )
    assert service.message(log("expense.created"), "Vale", "Expo", 1) is None
