"""Avisos al teléfono (Web Push): lo mismo que la campanita, aunque la app esté cerrada.

Cada vez que se confirma una transacción con movimientos de producción (los del audit log que
muestra Actividad), se manda un aviso a los dispositivos de los demás miembros de la
organización. Se manda en segundo plano, fuera del request: si el servicio de avisos tarda o
falla, nadie espera. Es gratis: lo entregan Google, Apple y Mozilla con sus propios servidores.
"""

import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, event, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import AppSession, DbContext, session_scope, set_context
from app.core.enums import Role
from app.core.errors import AppError
from app.core.security import utcnow
from app.modules.audit import AuditLog
from app.modules.events import Event
from app.modules.identity import Membership, MembershipStatus, User
from app.modules.push.models import PushKeys, PushSubscription

log = logging.getLogger(__name__)

# Solo estos servicios de avisos: el servidor nunca le hace POST a una dirección cualquiera.
PUSH_HOSTS = (
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    "push.services.mozilla.com",
    "web.push.apple.com",
    "notify.windows.com",
)
MAX_PER_USER = 10

_STATUS = {
    "DESIGN": "Diseño",
    "TO_BUY": "A comprar",
    "IN_WORKSHOP": "En taller",
    "READY": "Listo para carga",
    "MOUNTED": "Montado",
}
KINDS = {
    "piece.status_changed",
    "piece.update_posted",
    "piece.plan_uploaded",
    "production.started",
    "file.approval_decided",
}


def valid_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = parts.hostname or ""
    return parts.scheme == "https" and any(host == h or host.endswith(f".{h}") for h in PUSH_HOSTS)


# --- Claves ------------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def keys(db: AppSession) -> PushKeys:
    row = db.get(PushKeys, 1)
    if row is not None:
        return row
    vapid = Vapid02()
    vapid.generate_keys()
    private_pem = vapid.private_pem().decode()
    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    db.execute(
        insert(PushKeys)
        .values(id=1, private_pem=private_pem, public_key=_b64(public))
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return db.get(PushKeys, 1, populate_existing=True) or db.execute(select(PushKeys)).scalar_one()


# --- Suscripciones -----------------------------------------------------------------------


def subscribe(
    db: AppSession,
    user_id: UUID,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
) -> None:
    if not valid_endpoint(endpoint):
        raise AppError(422, "push_endpoint_invalid", "Este navegador no es compatible con avisos")
    count = len(
        db.execute(select(PushSubscription.id).where(PushSubscription.user_id == user_id)).all()
    )
    existing = db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    ).scalar_one_or_none()
    if existing is None and count >= MAX_PER_USER:
        raise AppError(409, "too_many_devices", "Ya tenés 10 dispositivos con avisos: sacá alguno")
    if existing is None:
        existing = PushSubscription(endpoint=endpoint)
        db.add(existing)
    existing.user_id = user_id  # el mismo navegador pasa a ser de quien entró
    existing.p256dh = p256dh
    existing.auth = auth
    existing.user_agent = (user_agent or "")[:400] or None


def unsubscribe(db: AppSession, user_id: UUID, endpoint: str) -> None:
    db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user_id, PushSubscription.endpoint == endpoint
        )
    )


def has_devices(db: AppSession, user_id: UUID) -> int:
    return len(
        db.execute(select(PushSubscription.id).where(PushSubscription.user_id == user_id)).all()
    )


# --- Mensajes ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    url: str


def message(
    entry: AuditLog, actor: str | None, event_name: str, event_number: int
) -> Message | None:
    """La misma frase que Actividad, en castellano."""
    after: dict[str, Any] = entry.after or {}
    who = actor or after.get("by") or "Alguien"
    piece = after.get("piece") or "una pieza"
    match entry.action:
        case "piece.status_changed":
            text = f"{who} pasó {piece} a {_STATUS.get(after.get('status', ''), 'otra fase')}"
        case "piece.update_posted":
            what = (
                "una foto de avance"
                if after.get("photo")
                else ("una nota de voz" if after.get("audio") else "una nota")
            )
            text = f"{who} dejó {what} en {piece}"
        case "piece.plan_uploaded":
            version = f" v{after['version']}" if after.get("version") else ""
            text = f"{who} subió {after.get('title') or 'un plano'}{version} de {piece}"
        case "production.started":
            text = f"{who} inició la producción"
        case "file.approval_decided":
            title = after.get("title") or "un diseño"
            if after.get("status") == "APPROVED":
                text = f"✓ {who} aprobó {title}"
            else:
                note = f": “{after['note']}”" if after.get("note") else ""
                text = f"{who} pidió cambios en {title}{note}"
        case _:
            return None
    return Message(
        title=f"#{event_number} {event_name}", body=text, url=f"/events/{entry.entity_id}"
    )


def _subject() -> str:
    """Quién manda (lo exige el estándar): la dirección pública de la app, que es https."""
    base = get_settings().app_base_url
    return base if base.startswith("https://") else "https://localhost"


def _send(subscription: PushSubscription, payload: Message, private_pem: str) -> bool:
    """Manda un aviso. False si el dispositivo ya no existe (se borra la suscripción)."""
    origin = urlsplit(subscription.endpoint)
    try:
        webpush(
            subscription_info={
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            },
            data=json.dumps({"title": payload.title, "body": payload.body, "url": payload.url}),
            vapid_private_key=Vapid02.from_pem(private_pem.encode()),
            vapid_claims={
                "sub": _subject(),
                "aud": f"{origin.scheme}://{origin.netloc}",
            },
            ttl=60 * 60 * 12,
            timeout=10,
        )
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (404, 410):
            return False
        log.warning("push failed (%s)", status)
    return True


def deliver(entries: list[tuple[UUID, UUID]]) -> None:
    """Para cada (organización, audit_log id): arma el texto y lo manda a los demás miembros."""
    for organization_id, entry_id in entries:
        try:
            with session_scope(DbContext(organization_id=organization_id)) as db:
                _deliver_one(db, organization_id, entry_id)
        except Exception:  # un aviso que falla no puede romper nada más
            log.exception("push delivery failed")


def _deliver_one(db: AppSession, organization_id: UUID, entry_id: UUID) -> None:
    entry = db.get(AuditLog, entry_id)
    if entry is None or entry.entity_id is None:
        return
    event_row = db.execute(
        select(Event.name, Event.number).where(
            Event.id == entry.entity_id, Event.organization_id == organization_id
        )
    ).first()
    if event_row is None:
        return
    actor = db.execute(select(User.name).where(User.id == entry.actor_user_id)).scalar_one_or_none()
    payload = message(entry, actor, event_row.name, event_row.number)
    if payload is None:
        return
    set_context(db, DbContext(organization_id=organization_id))
    # El taller solo ve lo suyo: no recibe avisos de todo el evento.
    members = db.execute(
        select(Membership.user_id).where(
            Membership.organization_id == organization_id,
            Membership.status == MembershipStatus.ACTIVE.value,
            Membership.role != Role.CREW.value,
        )
    ).scalars()
    recipients = {uid for uid in members if uid != entry.actor_user_id}
    if not recipients:
        return
    subscriptions = (
        db.execute(select(PushSubscription).where(PushSubscription.user_id.in_(recipients)))
        .scalars()
        .all()
    )
    if not subscriptions:
        return
    private_pem = keys(db).private_pem
    for subscription in subscriptions:
        if _send(subscription, payload, private_pem):
            subscription.last_sent_at = utcnow()
        else:
            db.delete(subscription)


def send_test(db: AppSession, user_id: UUID) -> int:
    """Un aviso de prueba a los dispositivos de quien lo pide."""
    subscriptions = (
        db.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
        .scalars()
        .all()
    )
    private_pem = keys(db).private_pem
    sent = 0
    payload = Message(
        title="Handie", body="¡Listo! Así te van a llegar los avisos.", url="/activity"
    )
    for subscription in subscriptions:
        if _send(subscription, payload, private_pem):
            sent += 1
        else:
            db.delete(subscription)
    return sent


# --- Enganche: después de cada commit con movimientos de producción ----------------------

_PENDING = "push_pending"
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="push")


def _after_flush(session: Session, _ctx: object) -> None:
    for obj in session.new:
        if isinstance(obj, AuditLog) and obj.action in KINDS and obj.entity_type == "event":
            session.info.setdefault(_PENDING, []).append((obj.organization_id, obj.id))


def _after_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING, None)
    if pending:
        _executor.submit(deliver, list(pending))


def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)


def install() -> None:
    """Se llama una vez al armar la app. Apagado en pruebas (no hay a quién mandar)."""
    if not get_settings().push_enabled or event.contains(AppSession, "after_commit", _after_commit):
        return
    event.listen(AppSession, "after_flush", _after_flush)
    event.listen(AppSession, "after_commit", _after_commit)
    event.listen(AppSession, "after_soft_rollback", lambda s, _p: _after_rollback(s))
