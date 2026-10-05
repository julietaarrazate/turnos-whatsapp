"""DTOs de la propuesta pública (ARCHITECTURE §8.4). `extra="forbid"` en todos: si el snapshot
trajera una clave que no está acá, la validación falla en lugar de publicarla."""

from datetime import date

from pydantic import BaseModel, ConfigDict

from app.modules.budgets import DisplayMode, IvaDisplay
from app.modules.proposals.models import ProposalStatus


class _Public(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicItem(_Public):
    description: str
    quantity: str
    unit: str
    days: int | None
    unit_price: str | None
    amount: str | None


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


class PublicProposal(_Public):
    status: ProposalStatus  # EXPIRED y SUPERSEDED se muestran en solo lectura
    can_decide: bool
    content_hash: str
    proposal: PublicSnapshot
    valid_until: date
