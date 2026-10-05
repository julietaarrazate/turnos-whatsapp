from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.pricing import service
from app.modules.pricing.schemas import (
    FxRateIn,
    FxRateOut,
    MarkupResolution,
    MarkupRuleIn,
    MarkupRuleOut,
    PricingSettings,
    PricingSettingsUpdate,
    SaleChargeIn,
    SaleChargeOut,
    SaleChargeUpdate,
)

router = APIRouter(prefix="/api/v1/pricing", tags=["pricing"])

# Markups, márgenes y cargos dejan inferir la ganancia: se leen con margin.view (PRODUCTION no).
View = Annotated[TenantContext, Depends(require(Permission.MARGIN_VIEW))]
Manage = Annotated[TenantContext, Depends(require(Permission.PRICING_SETTINGS))]
FxView = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
# El tipo de cambio es un dato de mercado: lo actualiza quien presupuesta.
FxRecord = Annotated[TenantContext, Depends(require(Permission.BUDGET_EDIT))]


@router.get("/settings")
def get_settings(ctx: View, db: DbSession) -> PricingSettings:
    return service.get_settings(db, ctx)


@router.patch("/settings")
def update_settings(body: PricingSettingsUpdate, ctx: Manage, db: DbSession) -> PricingSettings:
    return service.update_settings(db, ctx, body)


@router.get("/markup-rules")
def list_rules(ctx: View, db: DbSession) -> list[MarkupRuleOut]:
    return service.list_rules(db, ctx)


@router.put("/markup-rules")
def upsert_rule(body: MarkupRuleIn, ctx: Manage, db: DbSession) -> MarkupRuleOut:
    """Crea o reemplaza la regla del alcance. No cambia presupuestos existentes."""
    return service.upsert_rule(db, ctx, body)


@router.delete("/markup-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: UUID, ctx: Manage, db: DbSession) -> None:
    service.delete_rule(db, ctx, rule_id)


@router.get("/resolve")
def resolve(
    ctx: View, db: DbSession, product_id: UUID, client_id: UUID | None = None
) -> MarkupResolution:
    """Qué markup tomaría una línea nueva de ese producto para ese cliente, y de dónde sale."""
    return service.resolve(db, ctx, product_id, client_id)


@router.get("/sale-charges")
def list_sale_charges(ctx: View, db: DbSession) -> list[SaleChargeOut]:
    return service.list_sale_charges(db, ctx)


@router.post("/sale-charges", status_code=status.HTTP_201_CREATED)
def create_sale_charge(body: SaleChargeIn, ctx: Manage, db: DbSession) -> SaleChargeOut:
    return service.create_sale_charge(db, ctx, body)


@router.patch("/sale-charges/{charge_id}")
def update_sale_charge(
    charge_id: UUID, body: SaleChargeUpdate, ctx: Manage, db: DbSession
) -> SaleChargeOut:
    return service.update_sale_charge(db, ctx, charge_id, body)


@router.delete("/sale-charges/{charge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale_charge(charge_id: UUID, ctx: Manage, db: DbSession) -> None:
    service.delete_sale_charge(db, ctx, charge_id)


@router.get("/fx-rates")
def list_fx_rates(
    ctx: FxView, db: DbSession, limit: Annotated[int, Query(ge=1, le=100)] = 30
) -> list[FxRateOut]:
    """Historial, del más reciente al más viejo. El primero es el vigente."""
    return service.list_fx_rates(db, ctx, limit)


@router.post("/fx-rates", status_code=status.HTTP_201_CREATED)
def record_fx_rate(body: FxRateIn, ctx: FxRecord, db: DbSession) -> FxRateOut:
    return service.record_fx_rate(db, ctx, body)
