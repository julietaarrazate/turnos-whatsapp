from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.modules.events.models import EventStatus


class EventIn(BaseModel):
    """Cliente existente (`client_id`) o uno nuevo solo con el nombre (`client_name`)."""

    client_id: UUID | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    event_days: int = Field(default=1, ge=1, le=365)
    setup_days: int = Field(default=0, ge=0, le=60)
    teardown_days: int = Field(default=0, ge=0, le=60)
    venue: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    responsible_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _check(self) -> "EventIn":
        if (self.client_id is None) == (self.client_name is None):
            raise ValueError("Indicá un cliente existente o el nombre de uno nuevo")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
        return self


class EventUpdate(BaseModel):
    client_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    event_days: int | None = Field(default=None, ge=1, le=365)
    setup_days: int | None = Field(default=None, ge=0, le=60)
    teardown_days: int | None = Field(default=None, ge=0, le=60)
    venue: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    responsible_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class StatusChangeIn(BaseModel):
    to_status: EventStatus
    reason: str | None = Field(default=None, max_length=2000)


class StatusChangeOut(BaseModel):
    from_status: EventStatus | None
    to_status: EventStatus
    changed_by_name: str | None
    reason: str | None
    at: datetime


class EventSummary(BaseModel):
    id: UUID
    number: int
    name: str
    client_id: UUID
    client_name: str
    start_date: date | None
    end_date: date | None
    event_days: int
    city: str | None
    status: EventStatus
    responsible_name: str | None


class EventOut(EventSummary):
    setup_days: int
    teardown_days: int
    venue: str | None
    responsible_user_id: UUID | None
    lost_reason: str | None
    cancel_reason: str | None
    notes: str | None
    history: list[StatusChangeOut]


class EventPage(BaseModel):
    items: list[EventSummary]
    next_cursor: str | None
