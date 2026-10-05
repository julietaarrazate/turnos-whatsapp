from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.core.enums import TaxCondition
from app.domain.pricing import ChargeMode

CUIT_PATTERN = r"^\d{2}-?\d{8}-?\d$"


# --- Categorías y unidades -----------------------------------------------------------


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: UUID | None = None
    default_iva_rate: Decimal = Field(
        default=Decimal("0.21"), ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    sort: int = Field(default=0, ge=0, le=10_000)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: UUID | None = None
    default_iva_rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    sort: int | None = Field(default=None, ge=0, le=10_000)


class CategoryOut(BaseModel):
    id: UUID
    name: str
    parent_id: UUID | None
    default_iva_rate: Decimal
    sort: int


class UnitOut(BaseModel):
    id: UUID
    code: str
    name: str
    allows_decimals: bool


# --- Costos ----------------------------------------------------------------------------


class PriceIn(BaseModel):
    amount: Decimal = Field(ge=Decimal(0), max_digits=18, decimal_places=6)
    includes_iva: bool = False
    iva_rate: Decimal = Field(
        default=Decimal("0.21"), ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    valid_from: date | None = None  # por defecto, hoy (hora de Argentina)
    source_ref: str | None = Field(default=None, max_length=200)


class CostOut(BaseModel):
    amount: Decimal
    currency: str
    includes_iva: bool
    iva_rate: Decimal
    valid_from: date
    days_old: int
    stale: bool


class PriceOut(BaseModel):
    id: UUID
    amount: Decimal
    currency: str
    includes_iva: bool
    iva_rate: Decimal
    valid_from: date
    source: str
    source_ref: str | None
    created_by_name: str | None


# --- Proveedores -------------------------------------------------------------------------


class SupplierContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    is_primary: bool = False


class SupplierContactOut(BaseModel):
    id: UUID
    name: str
    email: str | None
    phone: str | None
    is_primary: bool


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, pattern=CUIT_PATTERN)
    tax_condition: TaxCondition | None = None
    payment_terms: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    rating: int | None = Field(default=None, ge=1, le=5)
    rating_notes: str | None = Field(default=None, max_length=2000)
    contacts: list[SupplierContactIn] = Field(default_factory=list, max_length=50)
    category_ids: list[UUID] = Field(default_factory=list, max_length=50)


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, pattern=CUIT_PATTERN)
    tax_condition: TaxCondition | None = None
    payment_terms: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    rating: int | None = Field(default=None, ge=1, le=5)
    rating_notes: str | None = Field(default=None, max_length=2000)
    contacts: list[SupplierContactIn] | None = Field(default=None, max_length=50)
    category_ids: list[UUID] | None = Field(default=None, max_length=50)


class SupplierSummary(BaseModel):
    id: UUID
    name: str
    is_internal: bool
    rating: int | None
    category_names: list[str]
    offers_count: int


class SupplierOfferOut(BaseModel):
    offer_id: UUID
    product_id: UUID
    product_name: str
    unit_code: str
    current_cost: CostOut | None  # None si no hay costo o sin permiso cost.view


class SupplierOut(BaseModel):
    id: UUID
    name: str
    legal_name: str | None
    tax_id: str | None
    tax_condition: TaxCondition | None
    payment_terms: str | None
    notes: str | None
    rating: int | None
    rating_notes: str | None
    is_internal: bool
    contacts: list[SupplierContactOut]
    category_ids: list[UUID]
    offers: list[SupplierOfferOut]


# --- Productos y ofertas -------------------------------------------------------------------


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category_id: UUID
    unit_id: UUID
    charge_mode: ChargeMode = ChargeMode.FIXED
    description_internal: str | None = Field(default=None, max_length=5000)
    description_client: str | None = Field(default=None, max_length=5000)
    min_quantity: Decimal | None = Field(
        default=None, gt=Decimal(0), max_digits=14, decimal_places=4
    )
    iva_rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: UUID | None = None
    unit_id: UUID | None = None
    charge_mode: ChargeMode | None = None
    description_internal: str | None = Field(default=None, max_length=5000)
    description_client: str | None = Field(default=None, max_length=5000)
    min_quantity: Decimal | None = Field(
        default=None, gt=Decimal(0), max_digits=14, decimal_places=4
    )
    iva_rate: Decimal | None = Field(
        default=None, ge=Decimal(0), lt=Decimal(1), max_digits=5, decimal_places=4
    )
    is_active: bool | None = None


class OfferIn(BaseModel):
    supplier_id: UUID
    supplier_sku: str | None = Field(default=None, max_length=80)
    is_preferred: bool = False
    notes: str | None = Field(default=None, max_length=2000)
    cost: PriceIn | None = None


class OfferUpdate(BaseModel):
    supplier_sku: str | None = Field(default=None, max_length=80)
    is_preferred: bool | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class OfferOut(BaseModel):
    id: UUID
    supplier_id: UUID
    supplier_name: str
    supplier_is_internal: bool
    supplier_rating: int | None
    supplier_sku: str | None
    is_preferred: bool
    is_active: bool
    notes: str | None
    current_cost: CostOut | None
    upcoming_cost: CostOut | None


class PreferredOffer(BaseModel):
    supplier_name: str
    current_cost: CostOut | None


class ProductSummary(BaseModel):
    id: UUID
    name: str
    category_id: UUID
    category_name: str
    unit_code: str
    charge_mode: ChargeMode
    is_active: bool
    offers_count: int
    preferred: PreferredOffer | None


class ProductOut(BaseModel):
    id: UUID
    name: str
    category_id: UUID
    unit_id: UUID
    charge_mode: ChargeMode
    description_internal: str | None
    description_client: str | None
    min_quantity: Decimal | None
    iva_rate: Decimal | None
    is_active: bool
    offers: list[OfferOut]


class ProductPage(BaseModel):
    items: list[ProductSummary]
    next_cursor: str | None
