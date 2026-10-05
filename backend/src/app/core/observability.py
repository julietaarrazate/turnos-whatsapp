"""Sentry (solo si hay DSN). Nunca se envían cookies, headers de auth, cuerpos ni importes."""

import re
from typing import Any

import sentry_sdk

from app.core.config import get_settings

_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-csrf-token"}
# Rutas cuyo último segmento es un token secreto (invitaciones, reset, propuestas públicas).
_TOKEN_PATHS = re.compile(r"/(invite|reset-password|invitations)/(?!accept\b)[^/?#]+")


def redact_tokens(url: str) -> str:
    return _TOKEN_PATHS.sub(r"/\1/[token]", url)


def _scrub(event: Any, _hint: Any) -> Any:
    request = event.get("request") or {}
    request.pop("data", None)  # cuerpos: pueden tener contraseñas, tokens o importes
    request.pop("cookies", None)
    request.pop("query_string", None)
    if isinstance(request.get("url"), str):
        request["url"] = redact_tokens(request["url"])
    if isinstance(event.get("transaction"), str):
        event["transaction"] = redact_tokens(event["transaction"])
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in _SENSITIVE_HEADERS:
            headers[key] = "[filtrado]"
    return event


def init_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=settings.release,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=_scrub,
        before_send_transaction=_scrub,
    )
