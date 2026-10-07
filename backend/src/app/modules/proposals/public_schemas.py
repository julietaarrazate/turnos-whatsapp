"""DTOs de la propuesta pública (ARCHITECTURE §8.4). `extra="forbid"` en todos: si el snapshot
trajera una clave que no está acá, la validación falla en lugar de publicarla."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.budgets import DisplayMode, IvaDisplay
from app.modules.proposals.models import ApprovalMethod, ProposalStatus


class _Public(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicItem(_Public):
    description: str
    quantity: str
    unit: str
    days: int | None
    unit_price: str | None
    amount: str | None
    price_label: str | None = None  # BONIFICADO / A_DEFINIR en lugar del importe


class PublicSection(_Public):
    title: str
    items: list[PublicItem]
    total: str | None


class PublicTotals(_Public):
    total: str
    subtotal: str | None = None
    global_discount: str | None = None
    net: str | None = None
    iva: str | None = None
    iva_included: str | None = None


class PublicParty(_Public):
    name: str | None


class PublicOrganization(_Public):
    name: str
    legal_name: str | None
    tax_id: str | None


class PublicEvent(_Public):
    name: str | None
    start_date: str | None
    end_date: str | None
    venue: str | None
    city: str | None


class PublicSnapshot(_Public):
    schema_version: int
    budget_number: int
    version_no: int
    proposal_number: int
    title: str
    currency: str
    display_mode: DisplayMode
    iva_display: IvaDisplay
    organization: PublicOrganization
    client: PublicParty
    event: PublicEvent
    sections: list[PublicSection]
    totals: PublicTotals
    valid_until: str
    terms: str | None
    payment_terms: str | None


class PublicDecision(_Public):
    status: ProposalStatus  # ACCEPTED o REJECTED
    decided_at: datetime
    decided_by_name: str | None
    method: ApprovalMethod | None  # MANUAL: la aprobó la productora (p. ej. con una OC)


class PublicProposal(_Public):
    status: ProposalStatus  # EXPIRED y SUPERSEDED se muestran en solo lectura
    can_decide: bool
    content_hash: str
    proposal: PublicSnapshot
    valid_until: date
    decision: PublicDecision | None


# --- Lo que manda el cliente --------------------------------------------------------------


class _Decision(_Public):
    # Lo que el cliente estaba viendo: si no coincide, no se registra la decisión (I7).
    content_hash: str = Field(min_length=64, max_length=64)


class AcceptIn(_Decision):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=320)
    comment: str | None = Field(default=None, max_length=2000)


class RejectIn(_Decision):
    reason: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = Field(default=None, max_length=320)
