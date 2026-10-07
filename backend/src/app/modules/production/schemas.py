from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.production.models import HireStatus, TaskStatus


class HireItem(BaseModel):
    line_key: UUID
    name: str
    quantity: Decimal
    unit_code: str
    days: int
    cost_total: Decimal | None  # solo con cost.view


class EventSupplierOut(BaseModel):
    id: UUID
    supplier_id: UUID | None
    supplier_name: str | None
    status: HireStatus
    budgeted_cost: Decimal | None  # solo con cost.view
    items: list[HireItem]
    notes: str | None
    invoice_number: str | None
    payment_terms: str | None
    confirmed_at: datetime | None
    paid_at: datetime | None


class EventSupplierUpdate(BaseModel):
    status: HireStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)
    invoice_number: str | None = Field(default=None, max_length=50)
    payment_terms: str | None = Field(default=None, max_length=200)


class TaskOut(BaseModel):
    id: UUID
    title: str
    status: TaskStatus
    assignee_user_id: UUID | None
    assignee_name: str | None
    due_date: date | None


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    assignee_user_id: UUID | None = None
    due_date: date | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: TaskStatus | None = None
    assignee_user_id: UUID | None = None
    due_date: date | None = None


class ProductionOut(BaseModel):
    started: bool
    suppliers: list[EventSupplierOut]
    tasks: list[TaskOut]
    budgeted_cost: Decimal | None  # total, solo con cost.view
