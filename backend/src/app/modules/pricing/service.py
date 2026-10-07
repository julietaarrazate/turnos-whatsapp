"""Reglas de pricing: markup, cargos sobre la venta, tipo de cambio y configuración."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.db import AppSession
from app.core.errors import AppError, ensure, not_found
from app.domain.pricing import (
    LineInput,
    MarkupRule,
    MarkupSource,
    PricingContext,
    ResolvedMarkup,
    RuleMode,
    SaleCharge,
    TaxCondition,
    resolve_markup,
)
from app.modules.audit import diff, record
from app.modules.auth import TenantContext
from app.modules.catalog import (
    DEFAULT_STALENESS_DAYS,
    STALENESS_SETTING,
    Category,
    Product,
    today_ar,
)
from app.modules.clients import Client
from app.modules.identity import Organization, User
from app.modules.pricing.models import FxRate, MarkupRuleRow, MarkupScope, SaleChargeRow
from app.modules.pricing.schemas import (
    FxCurrency,
    FxRateIn,
    FxRateOut,
    MarkupResolution,
    MarkupRuleIn,
    MarkupRuleOut,
    PricingSettings,
    PricingSettingsUpdate,
    RoundingIncrement,
    SaleChargeIn,
    SaleChargeOut,
    SaleChargeUpdate,
)

DEFAULT_ORG_MARKUP = Decimal("0.30")
ONE = Decimal(1)

# Claves en organizations.settings (la de antigüedad la comparte con el catálogo).
_ROUNDING = "rounding_increment"
_MIN_MARGIN = "min_margin"
_MARGIN_INCLUDES_CHARGES = "margin_includes_sale_charges"


def _audit(
    db: AppSession,
    ctx: TenantContext,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    **changes: Any,
) -> None:
    record(
        db,
        organization_id=ctx.organization_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=ctx.user_id,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
        **changes,
    )


def seed_pricing_defaults(db: AppSession, organization_id: UUID) -> None:
    """La regla general siempre existe (§5.3, paso 6). Requiere contexto de la organización."""
    db.add(
        MarkupRuleRow(
            organization_id=organization_id,
            scope=MarkupScope.ORG,
            mode=RuleMode.MARKUP,
            value=DEFAULT_ORG_MARKUP,
        )
    )
    db.flush()


# --- Configuración -------------------------------------------------------------------------


def _org(db: AppSession, ctx: TenantContext) -> Organization:
    return ensure(db.get(Organization, ctx.organization_id), "organización")


def settings_from(org_settings: dict[str, Any]) -> PricingSettings:
    staleness = org_settings.get(STALENESS_SETTING, DEFAULT_STALENESS_DAYS)
    min_margin = org_settings.get(_MIN_MARGIN)
    return PricingSettings(
        rounding_increment=RoundingIncrement(org_settings.get(_ROUNDING, RoundingIncrement.CENT)),
        min_margin=Decimal(min_margin) if min_margin is not None else None,
        margin_includes_sale_charges=bool(org_settings.get(_MARGIN_INCLUDES_CHARGES, True)),
        price_staleness_days=staleness if isinstance(staleness, int) else DEFAULT_STALENESS_DAYS,
    )


def _settings_json(settings: PricingSettings) -> dict[str, Any]:
    return {
        _ROUNDING: settings.rounding_increment.value,
        _MIN_MARGIN: str(settings.min_margin) if settings.min_margin is not None else None,
        _MARGIN_INCLUDES_CHARGES: settings.margin_includes_sale_charges,
        STALENESS_SETTING: settings.price_staleness_days,
    }


def get_settings(db: AppSession, ctx: TenantContext) -> PricingSettings:
    return settings_from(_org(db, ctx).settings)


def update_settings(
    db: AppSession, ctx: TenantContext, body: PricingSettingsUpdate
) -> PricingSettings:
    org = _org(db, ctx)
    current = settings_from(org.settings)
    updated = current.model_copy(update=body.model_dump(exclude_unset=True))
    # Si alguien manda null en un campo obligatorio, se conserva el valor actual.
    for field in ("rounding_increment", "margin_includes_sale_charges", "price_staleness_days"):
        if getattr(updated, field) is None:
            setattr(updated, field, getattr(current, field))
    before, after = diff(_settings_json(current), _settings_json(updated))
    if after:
        org.settings = {**org.settings, **_settings_json(updated)}
        _audit(
            db,
            ctx,
            "org.pricing_settings_changed",
            "organization",
            org.id,
            before=before,
            after=after,
        )
    return updated


# --- Reglas de markup ----------------------------------------------------------------------

Target = type[Category] | type[Product] | type[Client]
_SCOPE_MODELS: dict[MarkupScope, Target] = {
    MarkupScope.CATEGORY: Category,
    MarkupScope.PRODUCT: Product,
    MarkupScope.CLIENT: Client,
}


def _scope_names(db: AppSession, rules: list[MarkupRuleRow]) -> dict[UUID, str]:
    ids: dict[str, list[UUID]] = {}
    for rule in rules:
        if rule.scope_id is not None:
            ids.setdefault(rule.scope, []).append(rule.scope_id)
    names: dict[UUID, str] = {}
    for scope, model in _SCOPE_MODELS.items():
        if scope in ids:
            rows = db.execute(select(model.id, model.name).where(model.id.in_(ids[scope])))
            names.update({row.id: row.name for row in rows})
    return names


def _effective_markup(mode: str, value: Decimal) -> Decimal:
    if mode == RuleMode.MARGIN:
        return (value / (ONE - value)).quantize(Decimal("0.000001"))
    return value


def _rule_out(rule: MarkupRuleRow, names: dict[UUID, str]) -> MarkupRuleOut:
    return MarkupRuleOut(
        id=rule.id,
        scope=MarkupScope(rule.scope),
        scope_id=rule.scope_id,
        scope_name=names.get(rule.scope_id) if rule.scope_id else None,
        mode=RuleMode(rule.mode),
        value=rule.value,
        effective_markup=_effective_markup(rule.mode, rule.value),
        updated_at=rule.updated_at,
    )


_SCOPE_ORDER = {
    MarkupScope.ORG: 0,
    MarkupScope.CATEGORY: 1,
    MarkupScope.PRODUCT: 2,
    MarkupScope.CLIENT: 3,
}


def list_rules(db: AppSession, ctx: TenantContext) -> list[MarkupRuleOut]:
    rules = list(
        db.execute(
            select(MarkupRuleRow).where(MarkupRuleRow.organization_id == ctx.organization_id)
        ).scalars()
    )
    names = _scope_names(db, rules)
    out = [_rule_out(rule, names) for rule in rules]
    return sorted(out, key=lambda r: (_SCOPE_ORDER[r.scope], (r.scope_name or "").lower()))


def _check_scope_target(
    db: AppSession, ctx: TenantContext, scope: MarkupScope, scope_id: UUID
) -> None:
    model = _SCOPE_MODELS[scope]
    found = db.execute(
        select(model.id).where(
            model.id == scope_id,
            model.organization_id == ctx.organization_id,
            model.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if found is None:
        raise not_found()


def upsert_rule(db: AppSession, ctx: TenantContext, body: MarkupRuleIn) -> MarkupRuleOut:
    if body.scope_id is not None:
        _check_scope_target(db, ctx, body.scope, body.scope_id)
    rule = db.execute(
        select(MarkupRuleRow).where(
            MarkupRuleRow.organization_id == ctx.organization_id,
            MarkupRuleRow.scope == body.scope,
            MarkupRuleRow.scope_id.is_(None)
            if body.scope_id is None
            else MarkupRuleRow.scope_id == body.scope_id,
        )
    ).scalar_one_or_none()
    before = {"mode": rule.mode, "value": str(rule.value)} if rule else None
    if rule is None:
        rule = MarkupRuleRow(
            organization_id=ctx.organization_id, scope=body.scope, scope_id=body.scope_id
        )
        db.add(rule)
    rule.mode = body.mode
    rule.value = body.value
    db.flush()
    db.refresh(rule)
    after = {"scope": body.scope.value, "mode": body.mode.value, "value": str(body.value)}
    _audit(db, ctx, "markup_rule.changed", "markup_rule", rule.id, before=before, after=after)
    return _rule_out(rule, _scope_names(db, [rule]))


def delete_rule(db: AppSession, ctx: TenantContext, rule_id: UUID) -> None:
    rule = db.execute(
        select(MarkupRuleRow).where(
            MarkupRuleRow.id == rule_id, MarkupRuleRow.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if rule is None:
        raise not_found()
    if rule.scope == MarkupScope.ORG:
        raise AppError(
            409, "org_rule_required", "El markup general no se puede borrar, solo cambiar"
        )
    _audit(
        db,
        ctx,
        "markup_rule.changed",
        "markup_rule",
        rule.id,
        before={"scope": rule.scope, "mode": rule.mode, "value": str(rule.value)},
        after=None,
    )
    db.delete(rule)


def _to_domain(rule: MarkupRuleRow) -> MarkupRule:
    return MarkupRule(
        value=rule.value, mode=RuleMode(rule.mode), source_id=str(rule.scope_id or rule.id)
    )


def _domain_rule(rule: MarkupRuleRow | None) -> MarkupRule | None:
    return _to_domain(rule) if rule is not None else None


def _rule_for(
    db: AppSession, ctx: TenantContext, scope: MarkupScope, scope_id: UUID
) -> MarkupRuleRow | None:
    return db.execute(
        select(MarkupRuleRow).where(
            MarkupRuleRow.organization_id == ctx.organization_id,
            MarkupRuleRow.scope == scope,
            MarkupRuleRow.scope_id == scope_id,
        )
    ).scalar_one_or_none()


def client_rule(db: AppSession, ctx: TenantContext, client_id: UUID) -> MarkupRule | None:
    """La regla de markup propia de un cliente ("markup preferencial"), si tiene."""
    return _domain_rule(_rule_for(db, ctx, MarkupScope.CLIENT, client_id))


def active_sale_charges(db: AppSession, ctx: TenantContext) -> tuple[SaleCharge, ...]:
    rows = db.execute(
        select(SaleChargeRow)
        .where(
            SaleChargeRow.organization_id == ctx.organization_id,
            SaleChargeRow.is_active.is_(True),
            SaleChargeRow.applies_by_default.is_(True),
        )
        .order_by(SaleChargeRow.sort, SaleChargeRow.name)
    ).scalars()
    return tuple(SaleCharge(name=c.name, rate=c.rate) for c in rows)


def pricing_context(db: AppSession, ctx: TenantContext, client_id: UUID | None) -> PricingContext:
    """El contexto con el que el motor precia un presupuesto nuevo de ese cliente."""
    org = _org(db, ctx)
    settings = settings_from(org.settings)
    org_rule = db.execute(
        select(MarkupRuleRow).where(
            MarkupRuleRow.organization_id == ctx.organization_id,
            MarkupRuleRow.scope == MarkupScope.ORG,
        )
    ).scalar_one()
    client_rule = _rule_for(db, ctx, MarkupScope.CLIENT, client_id) if client_id else None
    return PricingContext(
        tax_condition=TaxCondition(org.tax_condition),
        org_rule=_to_domain(org_rule),
        client_rule=_domain_rule(client_rule),
        sale_charges=active_sale_charges(db, ctx),
        rounding_increment=Decimal(settings.rounding_increment.value),
        margin_includes_sale_charges=settings.margin_includes_sale_charges,
        min_margin=settings.min_margin,
    )


def line_rules(
    db: AppSession, ctx: TenantContext, product: Product
) -> tuple[MarkupRule | None, tuple[MarkupRule, ...]]:
    """Regla del producto y de su categoría (y de la categoría padre), en ese orden."""
    category = db.get(Category, product.category_id)
    category_ids = [product.category_id]
    if category is not None and category.parent_id is not None:
        category_ids.append(category.parent_id)
    category_rules = [_rule_for(db, ctx, MarkupScope.CATEGORY, cid) for cid in category_ids]
    return (
        _domain_rule(_rule_for(db, ctx, MarkupScope.PRODUCT, product.id)),
        tuple(r for r in (_domain_rule(rule) for rule in category_rules) if r is not None),
    )


def resolve(
    db: AppSession, ctx: TenantContext, product_id: UUID, client_id: UUID | None
) -> MarkupResolution:
    product = db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.organization_id == ctx.organization_id,
            Product.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if product is None:
        raise not_found()
    if client_id is not None:
        _check_scope_target(db, ctx, MarkupScope.CLIENT, client_id)
    pricing = pricing_context(db, ctx, client_id)
    product_rule, category_rules = line_rules(db, ctx, product)
    line = LineInput(
        key=str(product.id),
        quantity=ONE,
        unit_cost=ONE,
        product_rule=product_rule,
        category_rules=category_rules,
    )
    markup, source, source_id = resolve_markup(line, None, pricing)
    scope_id = UUID(source_id) if source_id and source is not MarkupSource.ORG else None
    source_name = None
    if scope_id is not None:
        model = _SCOPE_MODELS[MarkupScope(source.value)]
        source_name = db.execute(select(model.name).where(model.id == scope_id)).scalar_one()
    return MarkupResolution(
        markup=markup.quantize(Decimal("0.000001")),
        margin=(markup / (ONE + markup)).quantize(Decimal("0.000001")),
        source=source,
        source_id=scope_id,
        source_name=source_name,
    )


# --- Cargos sobre la venta -----------------------------------------------------------------


def _charge_out(c: SaleChargeRow) -> SaleChargeOut:
    return SaleChargeOut(
        id=c.id,
        name=c.name,
        rate=c.rate,
        is_active=c.is_active,
        applies_by_default=c.applies_by_default,
        sort=c.sort,
    )


def _charge_snapshot(c: SaleChargeRow) -> dict[str, Any]:
    return {
        "name": c.name,
        "rate": str(c.rate),
        "is_active": c.is_active,
        "applies_by_default": c.applies_by_default,
    }


def _flush_charge(db: AppSession) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        if "uq_sale_charges_org_name" in str(exc.orig):
            raise AppError(
                409, "sale_charge_name_taken", "Ya existe un cargo con ese nombre"
            ) from exc
        raise


def _charge(db: AppSession, ctx: TenantContext, charge_id: UUID) -> SaleChargeRow:
    charge = db.execute(
        select(SaleChargeRow).where(
            SaleChargeRow.id == charge_id, SaleChargeRow.organization_id == ctx.organization_id
        )
    ).scalar_one_or_none()
    if charge is None:
        raise not_found()
    return charge


def list_sale_charges(db: AppSession, ctx: TenantContext) -> list[SaleChargeOut]:
    rows = db.execute(
        select(SaleChargeRow)
        .where(SaleChargeRow.organization_id == ctx.organization_id)
        .order_by(SaleChargeRow.sort, func.lower(SaleChargeRow.name))
    ).scalars()
    return [_charge_out(c) for c in rows]


def create_sale_charge(db: AppSession, ctx: TenantContext, body: SaleChargeIn) -> SaleChargeOut:
    charge = SaleChargeRow(organization_id=ctx.organization_id, **body.model_dump())
    charge.name = charge.name.strip()
    db.add(charge)
    _flush_charge(db)
    _audit(
        db,
        ctx,
        "sale_charge.changed",
        "sale_charge",
        charge.id,
        before=None,
        after=_charge_snapshot(charge),
    )
    return _charge_out(charge)


def update_sale_charge(
    db: AppSession, ctx: TenantContext, charge_id: UUID, body: SaleChargeUpdate
) -> SaleChargeOut:
    charge = _charge(db, ctx, charge_id)
    before = _charge_snapshot(charge)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue  # todos los campos son obligatorios: null no borra
        setattr(charge, field, value.strip() if field == "name" else value)
    _flush_charge(db)
    old, new = diff(before, _charge_snapshot(charge))
    if new:
        _audit(db, ctx, "sale_charge.changed", "sale_charge", charge.id, before=old, after=new)
    return _charge_out(charge)


def delete_sale_charge(db: AppSession, ctx: TenantContext, charge_id: UUID) -> None:
    """Los presupuestos guardan una copia de los cargos que usaron: borrar no los afecta."""
    charge = _charge(db, ctx, charge_id)
    _audit(
        db,
        ctx,
        "sale_charge.changed",
        "sale_charge",
        charge.id,
        before=_charge_snapshot(charge),
        after=None,
    )
    db.delete(charge)


# --- Tipo de cambio ------------------------------------------------------------------------


def _fx_out(rate: FxRate, creator: str | None) -> FxRateOut:
    return FxRateOut(
        id=rate.id,
        currency=FxCurrency(rate.currency),
        rate=rate.rate,
        rate_date=rate.rate_date,
        source=rate.source,
        days_old=max((today_ar() - rate.rate_date).days, 0),
        created_by_name=creator,
        created_at=rate.created_at,
    )


def list_fx_rates(db: AppSession, ctx: TenantContext, limit: int = 30) -> list[FxRateOut]:
    """Del más reciente al más viejo. El primero es el que toman los presupuestos nuevos."""
    rows = db.execute(
        select(FxRate, User.name)
        .outerjoin(User, User.id == FxRate.created_by)
        .where(FxRate.organization_id == ctx.organization_id)
        .order_by(FxRate.rate_date.desc(), FxRate.created_at.desc(), FxRate.id.desc())
        .limit(limit)
    ).all()
    return [_fx_out(rate, name) for rate, name in rows]


def latest_fx_rate(db: AppSession, ctx: TenantContext, currency: str = "USD") -> FxRate | None:
    return db.execute(
        select(FxRate)
        .where(FxRate.organization_id == ctx.organization_id, FxRate.currency == currency)
        .order_by(FxRate.rate_date.desc(), FxRate.created_at.desc(), FxRate.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def record_fx_rate(db: AppSession, ctx: TenantContext, body: FxRateIn) -> FxRateOut:
    rate = FxRate(
        organization_id=ctx.organization_id,
        currency=body.currency.value,
        rate=body.rate,
        rate_date=body.rate_date or today_ar(),
        source="MANUAL",
        created_by=ctx.user_id,
    )
    db.add(rate)
    db.flush()
    db.refresh(rate)
    _audit(
        db,
        ctx,
        "fx_rate.recorded",
        "fx_rate",
        rate.id,
        after={
            "currency": rate.currency,
            "rate": str(rate.rate),
            "rate_date": rate.rate_date.isoformat(),
        },
    )
    user = db.get(User, ctx.user_id)
    return _fx_out(rate, user.name if user else None)


def resolve_line_markup(
    db: AppSession,
    ctx: TenantContext,
    *,
    product: Product | None,
    category_id: UUID | None,
    client_id: UUID | None,
) -> ResolvedMarkup:
    """El markup que toma una línea nueva (§5.3, pasos 3 a 6), para guardarlo en la línea."""
    if product is not None:
        product_rule, category_rules = line_rules(db, ctx, product)
    else:
        product_rule = None
        category_rules = ()
        if category_id is not None:
            category = db.get(Category, category_id)
            ids = [category_id] + ([category.parent_id] if category and category.parent_id else [])
            category_rules = tuple(
                r
                for r in (
                    _domain_rule(_rule_for(db, ctx, MarkupScope.CATEGORY, cid)) for cid in ids
                )
                if r is not None
            )
    pricing = pricing_context(db, ctx, client_id)
    line = LineInput(
        key="new",
        quantity=ONE,
        unit_cost=ONE,
        product_rule=product_rule,
        category_rules=category_rules,
    )
    markup, source, source_id = resolve_markup(line, None, pricing)
    return ResolvedMarkup(value=markup, source=source, source_id=source_id)
