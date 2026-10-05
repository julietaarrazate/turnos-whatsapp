from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import TaxCondition

CUIT_PATTERN = r"^\d{2}-?\d{8}-?\d$"


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    position: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    is_primary: bool = False


class ContactOut(BaseModel):
    id: UUID
    name: str
    position: str | None
    email: str | None
    phone: str | None
    is_primary: bool


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, pattern=CUIT_PATTERN)
    tax_condition: TaxCondition | None = None
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=5000)
    contacts: list[ContactIn] = Field(default_factory=list, max_length=50)


class ClientUpdate(BaseModel):
    """Solo se modifican los campos enviados. ``contacts`` reemplaza la lista completa."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, pattern=CUIT_PATTERN)
    tax_condition: TaxCondition | None = None
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=5000)
    contacts: list[ContactIn] | None = Field(default=None, max_length=50)


class ClientSummary(BaseModel):
    id: UUID
    name: str
    legal_name: str | None
    tax_id: str | None
    city: str | None
    primary_contact: str | None


class ClientOut(BaseModel):
    id: UUID
    name: str
    legal_name: str | None
    tax_id: str | None
    tax_condition: TaxCondition | None
    address: str | None
    city: str | None
    notes: str | None
    contacts: list[ContactOut]


class ClientPage(BaseModel):
    items: list[ClientSummary]
    next_cursor: str | None
