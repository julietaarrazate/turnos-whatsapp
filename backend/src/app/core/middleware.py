"""Request id de punta a punta y log de acceso estructurado."""

import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.observability import redact_tokens
from app.core.request_context import request_id_var

REQUEST_ID_HEADER = "X-Request-Id"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
log = structlog.get_logger()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_ID.match(incoming) else uuid4().hex
        token = request_id_var.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        if request.url.path not in ("/healthz", "/readyz"):
            log.info(
                "http.request",
                method=request.method,
                path=redact_tokens(request.url.path),
                status=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
        structlog.contextvars.clear_contextvars()
        return response
