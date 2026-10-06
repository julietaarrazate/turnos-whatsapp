"""Envío de emails: backend de consola (local/tests) o Resend."""

from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.errors import ensure
from app.modules.notifications.models import OutboundMessage

log = structlog.get_logger()


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    template: str
    reply_to: str | None = None  # p. ej. quien envió la propuesta, para que el cliente le responda


class EmailBackend(Protocol):
    def send(self, email: Email) -> str | None: ...


class ConsoleBackend:
    """Imprime el email en el log y lo guarda en memoria (los tests lo inspeccionan)."""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, email: Email) -> str | None:
        self.sent.append(email)
        log.info("email.console", to=email.to, subject=email.subject, body=email.text)
        return None


class ResendBackend:
    def send(self, email: Email) -> str | None:
        settings = get_settings()
        api_key = ensure(settings.resend_api_key, "RESEND_API_KEY")
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            json={
                "from": settings.email_from,
                "to": [email.to],
                "subject": email.subject,
                "text": email.text,
                **({"reply_to": email.reply_to} if email.reply_to else {}),
            },
            timeout=10,
        )
        response.raise_for_status()
        message_id = response.json().get("id")
        return str(message_id) if message_id else None


console_backend = ConsoleBackend()


def _backend() -> EmailBackend:
    return ResendBackend() if get_settings().email_backend == "resend" else console_backend


def send_email(email: Email) -> None:
    """Envía y registra el resultado. Pensado para correr en una BackgroundTask post-commit."""
    status, provider_id, error = "SENT", None, None
    try:
        provider_id = _backend().send(email)
    except Exception as exc:  # el error queda registrado; el usuario puede reintentar
        status, error = "FAILED", repr(exc)[:2000]
        log.exception("email.failed", to=email.to, template=email.template)
    with session_scope() as session:
        session.add(
            OutboundMessage(
                to_email=email.to,
                template=email.template,
                subject=email.subject,
                status=status,
                provider_message_id=provider_id,
                error=error,
            )
        )
