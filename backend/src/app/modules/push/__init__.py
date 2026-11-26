"""Avisos al teléfono (Web Push), opcionales por persona y por dispositivo."""

from app.modules.push.router import router
from app.modules.push.service import install

__all__ = ["install", "router"]
