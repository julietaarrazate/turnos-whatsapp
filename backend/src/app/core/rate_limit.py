"""Rate limiting en memoria (una instancia). Al escalar a >1 instancia: store compartido (D-15)."""

import threading
import time
from collections import defaultdict, deque

from app.core.config import get_settings
from app.core.errors import AppError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Registra un intento. Devuelve False si se superó el límite en la ventana."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def enforce(key: str, limit: int, window_seconds: int) -> None:
    if get_settings().rate_limit_enabled and not limiter.hit(key, limit, window_seconds):
        raise AppError(429, "rate_limited", "Demasiados intentos. Probá de nuevo en unos minutos.")
