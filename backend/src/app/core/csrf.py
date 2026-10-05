"""Protección CSRF para autenticación por cookies (ARCHITECTURE §8.3).

Toda mutación debe traer ``X-Requested-With`` (un formulario cross-site no puede agregarlo
sin preflight CORS) y, si el browser envía ``Origin``, debe ser un origen permitido.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import problem

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-requested-with"


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
            if request.headers.get("authorization", "").lower().startswith("bearer "):
                return await call_next(request)
            settings = get_settings()
            origin = request.headers.get("origin")
            allowed = {*settings.allowed_origins, settings.app_base_url}
            if origin is not None and origin not in allowed:
                return problem(403, "csrf_origin", "Origen no permitido")
            if not request.headers.get(CSRF_HEADER):
                return problem(403, "csrf_header", "Falta el header X-Requested-With")
        return await call_next(request)
