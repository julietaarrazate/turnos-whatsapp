from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.budgets import DisplayMode, IvaDisplay
from app.modules.proposals.models import ProposalStatus


class ProposalIn(BaseModel):
    """Generar propuesta (P-01). Sin `version_no`, congela el borrador (con If-Match) o toma
    la última versión guardada."""

    version_no: int | None = Field(default=None, ge=1)
    display_mode: DisplayMode = DisplayMode.BY_SECTION
    iva_display: IvaDisplay = IvaDisplay.PLUS_IVA
    valid_days: int = Field(default=7, ge=1, le=120)
    terms: str | None = Field(default=None, max_length=5000)
    payment_terms: str | None = Field(default=None, max_length=2000)


class ProposalOut(BaseModel):
    id: UUID
    number: int
    budget_id: UUID
    version_no: int
    status: ProposalStatus
    display_mode: DisplayMode
    iva_display: IvaDisplay
    valid_until: date
    total: str
    currency: str
    sent_at: datetime
    first_viewed_at: datetime | None
    last_viewed_at: datetime | None
    view_count: int
    content_hash: str


class ProposalCreated(BaseModel):
    proposal: ProposalOut
    # Solo se muestra al generar: en la base queda el hash (§8.4).
    public_path: str
