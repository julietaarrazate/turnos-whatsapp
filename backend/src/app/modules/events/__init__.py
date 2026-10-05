"""Eventos: cliente, fechas, estado y responsable (DOMAIN_MODEL §2.5 y §3.1)."""

from app.modules.events.models import Event, EventStatus
from app.modules.events.router import router
from app.modules.events.schemas import EventIn
from app.modules.events.service import can_quote, create_event, get_event, on_budget_created

__all__ = [
    "Event",
    "EventIn",
    "EventStatus",
    "can_quote",
    "create_event",
    "get_event",
    "on_budget_created",
    "router",
]
