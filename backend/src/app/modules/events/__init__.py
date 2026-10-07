"""Eventos: cliente, fechas, estado y responsable (DOMAIN_MODEL §2.5 y §3.1)."""

from app.modules.events.models import Event, EventStatus
from app.modules.events.router import router
from app.modules.events.schemas import EventIn
from app.modules.events.service import (
    Actor,
    accepts_decisions,
    can_quote,
    create_event,
    get_event,
    notification_recipients,
    on_budget_created,
    on_proposal_accepted,
    on_proposal_sent,
    start_production,
)

__all__ = [
    "Actor",
    "Event",
    "EventIn",
    "EventStatus",
    "accepts_decisions",
    "can_quote",
    "create_event",
    "get_event",
    "notification_recipients",
    "on_budget_created",
    "on_proposal_accepted",
    "on_proposal_sent",
    "router",
    "start_production",
]
