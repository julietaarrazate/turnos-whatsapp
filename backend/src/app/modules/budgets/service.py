"""Presupuestos: versiones, secciones y líneas, recalculadas por el motor en cada cambio.

Reglas (DOMAIN_MODEL §2.6, §3.2, §5; ARCHITECTURE §4.4–4.5):
- Toda mutación del borrador recalcula la versión completa y devuelve el resultado.
- Lock optimista: cada mutación trae el `lock_version` que vio el cliente (If-Match). Si no
  coincide, 409 y no se aplica nada.
- Los importes los produce solo el motor (I8): la API no acepta campos calculados.
- Una versión FROZEN no cambia nunca (servicio + trigger).
"""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select, tuple_
from sqlalchemy.orm import aliased

from app.core.counters import next_number
from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.core.permissions import Permission
from app.core.security import utcnow
from app.domain.pricing import (
    ChargeMode,
    LineInput,
    LinePricingMode,
    MarkupRule,
    MarkupSource,
    PricingContext,
    PricingError,
    ResolvedMarkup,
    RuleMode,
    SaleCharge,
    TaxCondition,
    VersionInput,
    VersionPriced,
    VersionPricingMode,
    present_in_currency,
    price_version,
)
from app.modules.audit import diff, record
from app.modules.auth import TenantContext
from app.modules.budgets.export import version_xlsx
from app.modules.budgets.models import (
    Budget,
    BudgetCurrency,
    BudgetLine,
    BudgetSection,
    BudgetVersion,
    ClientPriceLabel,
    VersionStatus,
)
from app.modules.budgets.schemas import (
    BudgetCreate,
    BudgetEvent,
    BudgetOut,
    BudgetPage,
    BudgetSummary,
    ChargeOut,
    ChargeRate,
    CompareOut,
    CostChange,
    CostsPreview,
    DiffKind,
    DuplicateIn,
    DuplicateOut,
    FieldChange,
    FreezeIn,
    FxOut,
    LineCost,
    LineDiff,
    LineIn,
    LineMargin,
    LineOut,
    LineUpdate,
    PresentationOut,
    RefreshCostsIn,
    RuleChange,
    RulesPreview,
    SectionIn,
    SectionOut,
    SectionUpdate,
    TotalsDelta,
    VersionCosts,
    VersionMargins,
    VersionOut,
    VersionSummary,
    VersionUpdate,
)
from app.modules.catalog import Product, category_info, current_prices, line_source, today_ar
from app.modules.clients import Client
from app.modules.events import (
    Event,
    EventStatus,
    can_quote,
    create_event,
    get_event,
    on_budget_created,
)
from app.modules.identity import Organization
from app.modules.pricing import latest_fx_rate, pricing_context, resolve_line_markup, settings_from

SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_SECTION_TITLE = "General"
UNIT = Decimal("0.000001")


def _audit(
    db: AppSession, ctx: TenantContext, action: str, entity_id: UUID, **changes: Any
) -> None:
    record(
        db,
        organization_id=ctx.organization_id,
        action=action,
        entity_type="budget",
        entity_id=entity_id,
        actor_user_id=ctx.user_id,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
        **changes,
    )


def _jsonable(values: dict[str, Any]) -> dict[str, Any]:
    return {
        k: (str(v) if v is not None and not isinstance(v, str | int | bool) else v)
        for k, v in values.items()
    }


# --- Contexto del motor (snapshot) -------------------------------------------------------


def _context_json(ctx: PricingContext) -> dict[str, Any]:
    def rule(r: MarkupRule | None) -> dict[str, Any] | None:
        return (
            None
            if r is None
            else {"value": str(r.value), "mode": r.mode.value, "source_id": r.source_id}
        )

    return {
        "tax_condition": ctx.tax_condition.value,
        "org_rule": rule(ctx.org_rule),
        "client_rule": rule(ctx.client_rule),
        "sale_charges": [{"name": c.name, "rate": str(c.rate)} for c in ctx.sale_charges],
        "rounding_increment": str(ctx.rounding_increment),
        "margin_includes_sale_charges": ctx.margin_includes_sale_charges,
        "default_iva_rate": str(ctx.default_iva_rate),
        "min_margin": str(ctx.min_margin) if ctx.min_margin is not None else None,
    }


def _context_from(data: dict[str, Any]) -> PricingContext:
    def rule(r: dict[str, Any] | None) -> MarkupRule | None:
        if r is None:
            return None
        return MarkupRule(Decimal(r["value"]), RuleMode(r["mode"]), r.get("source_id"))

    org_rule = rule(data["org_rule"])
    if org_rule is None:  # pragma: no cover - el snapshot siempre la trae
        raise RuntimeError("context_snapshot sin org_rule")
    return PricingContext(
        tax_condition=TaxCondition(data["tax_condition"]),
        org_rule=org_rule,
        client_rule=rule(data.get("client_rule")),
        sale_charges=tuple(SaleCharge(c["name"], Decimal(c["rate"])) for c in data["sale_charges"]),
        rounding_increment=Decimal(data["rounding_increment"]),
        margin_includes_sale_charges=bool(data["margin_includes_sale_charges"]),
        default_iva_rate=Decimal(data["default_iva_rate"]),
        min_margin=Decimal(data["min_margin"]) if data.get("min_margin") is not None else None,
    )


def _fx_snapshot(db: AppSession, ctx: TenantContext, currency: str) -> dict[str, Any] | None:
    if currency == BudgetCurrency.ARS:
        return None
    rate = latest_fx_rate(db, ctx, currency)
    if rate is None:
        raise AppError(
            422, "fx_rate_required", "Cargá un tipo de cambio antes de presupuestar en dólares"
        )
    return {
        currency: {
            "rate": str(rate.rate),
            "date": rate.rate_date.isoformat(),
            "source": rate.source,
        }
    }


# --- Carga y lock --------------------------------------------------------------------------


def _budget(db: AppSession, ctx: TenantContext, budget_id: UUID) -> Budget:
    budget = db.execute(
        select(Budget).where(Budget.id == budget_id, Budget.organization_id == ctx.organization_id)
    ).scalar_one_or_none()
    if budget is None:
        raise not_found()
    return budget


def ensure_budget(db: AppSession, ctx: TenantContext, budget_id: UUID) -> None:
    """404 si el presupuesto no existe en la organización (para módulos que cuelgan de él)."""
    _budget(db, ctx, budget_id)


def parse_if_match(raw: str) -> int:
    """`If-Match: 7` o `If-Match: "7"` (ETag débil o fuerte) → 7."""
    value = raw.strip().removeprefix("W/").strip('"')
    try:
        return int(value)
    except ValueError as exc:
        raise AppError(422, "if_match_invalid", "If-Match debe ser el lock_version") from exc


def _draft(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int
) -> tuple[Budget, BudgetVersion]:
    budget = _budget(db, ctx, budget_id)
    version = db.execute(
        select(BudgetVersion)
        .where(BudgetVersion.budget_id == budget.id, BudgetVersion.status == VersionStatus.DRAFT)
        .with_for_update()
    ).scalar_one_or_none()
    if version is None:
        raise AppError(409, "budget_no_draft", "Este presupuesto no tiene un borrador para editar")
    if version.lock_version != if_match:
        raise AppError(
            409,
            "budget_version_conflict",
            "El presupuesto cambió mientras lo editabas. Recargá para ver la última versión.",
            lock_version=version.lock_version,
        )
    return budget, version


def _sections(db: AppSession, version_id: UUID) -> list[BudgetSection]:
    return list(
        db.execute(
            select(BudgetSection)
            .where(BudgetSection.version_id == version_id)
            .order_by(BudgetSection.sort, BudgetSection.id)
        ).scalars()
    )


def _lines(db: AppSession, version_id: UUID) -> list[BudgetLine]:
    return list(
        db.execute(
            select(BudgetLine)
            .join(BudgetSection, BudgetSection.id == BudgetLine.section_id)
            .where(BudgetLine.version_id == version_id)
            .order_by(BudgetSection.sort, BudgetSection.id, BudgetLine.sort, BudgetLine.id)
        ).scalars()
    )


def _section(db: AppSession, version: BudgetVersion, section_id: UUID) -> BudgetSection:
    section = db.execute(
        select(BudgetSection).where(
            BudgetSection.id == section_id, BudgetSection.version_id == version.id
        )
    ).scalar_one_or_none()
    if section is None:
        raise not_found()
    return section


def _line(db: AppSession, version: BudgetVersion, line_id: UUID) -> BudgetLine:
    line = db.execute(
        select(BudgetLine).where(BudgetLine.id == line_id, BudgetLine.version_id == version.id)
    ).scalar_one_or_none()
    if line is None:
        raise not_found()
    return line


def _renumber[T: (BudgetSection, BudgetLine)](
    items: list[T], moved: T, position: int | None
) -> None:
    """Ubica `moved` en `position` (o al final) y deja `sort` = 0..n-1."""
    rest = [item for item in items if item.id != moved.id]
    index = len(rest) if position is None else min(position, len(rest))
    rest.insert(index, moved)
    for sort, item in enumerate(rest):
        item.sort = sort


# --- Recálculo -------------------------------------------------------------------------------


def _line_input(line: BudgetLine) -> LineInput:
    return LineInput(
        key=str(line.id),
        quantity=line.quantity,
        unit_cost=line.unit_cost_amount,
        days=line.days,
        charge_mode=ChargeMode(line.charge_mode),
        cost_includes_iva=line.unit_cost_includes_iva,
        cost_iva_rate=line.unit_cost_iva_rate,
        cost_is_total=line.cost_is_total,
        iva_rate=line.iva_rate,
        pricing_mode=LinePricingMode(line.pricing_mode),
        markup_manual=line.markup_manual,
        target_margin=line.target_margin,
        target_price=line.target_price,
        discount_rate=line.discount_rate,
        locked=line.is_locked,
        resolved=ResolvedMarkup(
            line.rule_markup, MarkupSource(line.rule_source), line.rule_source_id
        ),
    )


def _price(
    version: BudgetVersion,
    lines: list[BudgetLine],
    *,
    context: dict[str, Any] | None = None,
    overrides: dict[UUID, dict[str, Any]] | None = None,
) -> tuple[VersionInput, PricingContext, VersionPriced]:
    """Corre el motor sobre la versión. `context` y `overrides` (por línea) permiten simular
    cambios sin tocar la base (vista previa de "actualizar costos" o "re-aplicar reglas")."""
    pricing = _context_from(context or version.context_snapshot)
    inputs = []
    for line in lines:
        item = _line_input(line)
        if overrides and line.id in overrides:
            item = replace(item, **overrides[line.id])
        inputs.append(item)
    version_input = VersionInput(
        lines=tuple(inputs),
        mode=VersionPricingMode(version.pricing_mode),
        markup_override=version.markup_override,
        target_margin=version.target_margin,
        target_price=version.target_price,
        target_includes_iva=version.target_includes_iva,
        global_discount_rate=version.global_discount_rate,
        management_fee_rate=version.management_fee_rate,
    )
    try:
        return version_input, pricing, price_version(version_input, pricing)
    except PricingError as exc:
        raise AppError(422, f"pricing_{exc.code}", exc.detail) from exc


def _recalculate(db: AppSession, budget: Budget, version: BudgetVersion) -> None:
    """Recalcula la versión completa con el motor y sube el `lock_version`."""
    lines = _lines(db, version.id)
    version_input, pricing, result = _price(version, lines)

    for line, priced in zip(lines, result.lines, strict=True):
        line.unit_cost_effective = priced.unit_cost_effective.quantize(UNIT)
        line.fx_rate = Decimal(1)
        line.cost_total = priced.cost_total
        line.markup_applied = priced.markup_applied
        line.markup_source = priced.markup_source.value
        line.markup_source_id = priced.markup_source_id
        line.sale_list_total = priced.sale_list_total
        line.sale_total = priced.sale_total
        line.profit = priced.profit
        line.margin = priced.margin
        line.allocated_global_discount = priced.allocated_global_discount

    version.cost_direct = result.cost_direct
    version.sale_subtotal = result.sale_subtotal
    version.global_discount = result.global_discount
    version.management_fee = result.management_fee
    version.sale_net = result.sale_net
    version.sale_charges = result.sale_charges_total
    version.sale_charges_detail = [
        {"name": c.name, "rate": str(c.rate), "amount": str(c.amount)} for c in result.sale_charges
    ]
    version.profit = result.profit
    version.markup = result.markup
    version.margin_gross = result.margin_gross
    version.margin_net = result.margin_net
    version.iva = result.iva
    version.total = result.total
    version.warnings = [w.value for w in result.warnings]
    version.pricing_engine_version = result.engine_version

    version.presentation = None
    fx = (version.fx_snapshot or {}).get(budget.currency)
    if budget.currency != BudgetCurrency.ARS and fx is not None:
        shown = present_in_currency(
            result, version_input, pricing, budget.currency, Decimal(fx["rate"])
        )
        version.presentation = {
            "currency": shown.currency,
            "fx_rate": str(shown.fx_rate),
            "subtotal": str(shown.subtotal),
            "global_discount": str(shown.global_discount),
            "management_fee": str(shown.management_fee),
            "net": str(shown.net),
            "iva": str(shown.iva),
            "total": str(shown.total),
            "lines": {key: str(amount) for key, amount in shown.lines.items()},
        }
    version.lock_version += 1
    db.flush()


# --- Salida (con redacción por permisos) -------------------------------------------------------


def _line_out(line: BudgetLine, ctx: TenantContext, today: Any, stale_after: int) -> LineOut:
    days_old = max((today - line.cost_as_of).days, 0) if line.cost_as_of else None
    return LineOut(
        id=line.id,
        line_key=line.line_key,
        section_id=line.section_id,
        sort=line.sort,
        product_id=line.product_id,
        category_id=line.category_id,
        category_name=line.category_name,
        supplier_id=line.supplier_id,
        supplier_name=line.supplier_name,
        name_internal=line.name_internal,
        description_client=line.description_client,
        notes_internal=line.notes_internal,
        show_on_proposal=line.show_on_proposal,
        client_price_label=ClientPriceLabel(line.client_price_label)
        if line.client_price_label
        else None,
        unit_code=line.unit_code,
        charge_mode=ChargeMode(line.charge_mode),
        iva_rate=line.iva_rate,
        quantity=line.quantity,
        days=line.days,
        pricing_mode=LinePricingMode(line.pricing_mode),
        target_price=line.target_price,
        discount_rate=line.discount_rate,
        is_locked=line.is_locked,
        sale_list_total=line.sale_list_total,
        sale_total=line.sale_total,
        allocated_global_discount=line.allocated_global_discount,
        cost=LineCost(
            unit_cost_amount=line.unit_cost_amount,
            unit_cost_includes_iva=line.unit_cost_includes_iva,
            unit_cost_iva_rate=line.unit_cost_iva_rate,
            cost_is_total=line.cost_is_total,
            unit_cost_effective=line.unit_cost_effective,
            cost_total=line.cost_total,
            cost_as_of=line.cost_as_of,
            cost_days_old=days_old,
            cost_stale=days_old is not None and days_old > stale_after,
            supplier_product_id=line.supplier_product_id,
        )
        if ctx.can(Permission.COST_VIEW)
        else None,
        margin=LineMargin(
            markup_manual=line.markup_manual,
            target_margin=line.target_margin,
            rule_markup=line.rule_markup,
            rule_source=MarkupSource(line.rule_source),
            markup_applied=line.markup_applied,
            markup_source=MarkupSource(line.markup_source) if line.markup_source else None,
            profit=line.profit,
            margin=line.margin,
        )
        if ctx.can(Permission.MARGIN_VIEW)
        else None,
    )


def _version_out(
    db: AppSession, ctx: TenantContext, budget: Budget, version: BudgetVersion
) -> VersionOut:
    org = db.get(Organization, ctx.organization_id)
    stale_after = settings_from(org.settings if org else {}).price_staleness_days
    today = today_ar()
    lines = _lines(db, version.id)
    by_section: dict[UUID, list[BudgetLine]] = {}
    for line in lines:
        by_section.setdefault(line.section_id, []).append(line)
    pricing = version.context_snapshot
    fx = (version.fx_snapshot or {}).get(budget.currency)
    margins_visible = ctx.can(Permission.MARGIN_VIEW)
    return VersionOut(
        id=version.id,
        version_no=version.version_no,
        status=VersionStatus(version.status),
        lock_version=version.lock_version,
        pricing_mode=VersionPricingMode(version.pricing_mode),
        target_price=version.target_price,
        target_includes_iva=version.target_includes_iva,
        global_discount_rate=version.global_discount_rate,
        management_fee_rate=version.management_fee_rate,
        sale_subtotal=version.sale_subtotal,
        global_discount=version.global_discount,
        management_fee=version.management_fee,
        sale_net=version.sale_net,
        iva=version.iva,
        total=version.total,
        rounding_increment=Decimal(pricing["rounding_increment"]),
        fx=FxOut(currency=budget.currency, rate=Decimal(fx["rate"]), rate_date=fx["date"])
        if fx
        else None,
        presentation=PresentationOut(**version.presentation) if version.presentation else None,
        costs=VersionCosts(cost_direct=version.cost_direct)
        if ctx.can(Permission.COST_VIEW)
        else None,
        margins=VersionMargins(
            markup_override=version.markup_override,
            target_margin=version.target_margin,
            sale_charges=version.sale_charges,
            sale_charges_detail=[ChargeOut(**c) for c in version.sale_charges_detail],
            profit=version.profit,
            markup=version.markup,
            margin_gross=version.margin_gross,
            margin_net=version.margin_net,
            min_margin=Decimal(pricing["min_margin"]) if pricing.get("min_margin") else None,
        )
        if margins_visible
        else None,
        # "Por debajo del costo" o "del margen mínimo" revelan el margen.
        warnings=version.warnings if margins_visible else [],
        sections=[
            SectionOut(
                id=section.id,
                section_key=section.section_key,
                title_client=section.title_client,
                sort=section.sort,
                sale_total=sum(
                    (line.sale_total for line in by_section.get(section.id, [])), Decimal(0)
                ),
                lines=[
                    _line_out(line, ctx, today, stale_after)
                    for line in by_section.get(section.id, [])
                ],
            )
            for section in _sections(db, version.id)
        ],
        change_note=version.change_note,
        frozen_at=version.frozen_at,
        updated_at=version.updated_at,
    )


def _versions(db: AppSession, budget_id: UUID) -> list[BudgetVersion]:
    return list(
        db.execute(
            select(BudgetVersion)
            .where(BudgetVersion.budget_id == budget_id)
            .order_by(BudgetVersion.version_no)
        ).scalars()
    )


def budget_out(
    db: AppSession, ctx: TenantContext, budget: Budget, version: BudgetVersion | None = None
) -> BudgetOut:
    versions = _versions(db, budget.id)
    if version is None:
        drafts = [v for v in versions if v.status == VersionStatus.DRAFT]
        version = drafts[0] if drafts else versions[-1]
    event = db.get(Event, budget.event_id)
    if event is None:  # pragma: no cover - FK
        raise not_found()
    client_name = db.execute(select(Client.name).where(Client.id == event.client_id)).scalar_one()
    db.refresh(version)
    return BudgetOut(
        id=budget.id,
        number=budget.number,
        title=budget.title,
        currency=BudgetCurrency(budget.currency),
        event=BudgetEvent(
            id=event.id,
            number=event.number,
            name=event.name,
            client_id=event.client_id,
            client_name=client_name,
            start_date=event.start_date,
            event_days=event.event_days,
            status=EventStatus(event.status),
        ),
        version=_version_out(db, ctx, budget, version),
        versions=[
            VersionSummary(
                id=v.id,
                version_no=v.version_no,
                status=VersionStatus(v.status),
                sale_net=v.sale_net,
                total=v.total,
                change_note=v.change_note,
                frozen_at=v.frozen_at,
                updated_at=v.updated_at,
            )
            for v in versions
        ],
    )


# --- Lectura -------------------------------------------------------------------------------


def _encode_cursor(updated_at: datetime, budget_id: UUID) -> str:
    return urlsafe_b64encode(f"{updated_at.isoformat()}|{budget_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw_at, raw_id = urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(raw_at), UUID(raw_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError(422, "invalid_cursor", "Cursor inválido") from exc


def list_budgets(
    db: AppSession,
    ctx: TenantContext,
    *,
    q: str | None,
    event_id: UUID | None,
    cursor: str | None,
    limit: int,
) -> BudgetPage:
    """Cada presupuesto con su versión vigente (el borrador o la última congelada)."""
    latest = (
        select(BudgetVersion.budget_id, func.max(BudgetVersion.version_no).label("version_no"))
        .group_by(BudgetVersion.budget_id)
        .subquery()
    )
    accepted = aliased(BudgetVersion)
    query = (
        select(Budget, BudgetVersion, Event, Client.name, accepted.version_no)
        .join(latest, latest.c.budget_id == Budget.id)
        .join(
            BudgetVersion,
            (BudgetVersion.budget_id == Budget.id)
            & (BudgetVersion.version_no == latest.c.version_no),
        )
        .join(Event, Event.id == Budget.event_id)
        .join(Client, Client.id == Event.client_id)
        .outerjoin(
            accepted,
            (accepted.id == Event.accepted_budget_version_id) & (accepted.budget_id == Budget.id),
        )
        .where(Budget.organization_id == ctx.organization_id, Event.deleted_at.is_(None))
    )
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Budget.title).like(pattern),
                func.lower(Event.name).like(pattern),
                func.lower(Client.name).like(pattern),
            )
        )
    if event_id is not None:
        query = query.where(Budget.event_id == event_id)
    if cursor:
        at, last_id = _decode_cursor(cursor)
        query = query.where(tuple_(BudgetVersion.updated_at, Budget.id) < tuple_(at, last_id))
    rows = db.execute(
        query.order_by(BudgetVersion.updated_at.desc(), Budget.id.desc()).limit(limit + 1)
    ).all()
    page = rows[:limit]
    return BudgetPage(
        items=[
            BudgetSummary(
                id=budget.id,
                number=budget.number,
                title=budget.title,
                currency=BudgetCurrency(budget.currency),
                event_id=event.id,
                event_name=event.name,
                event_status=EventStatus(event.status),
                client_name=client_name,
                version_no=version.version_no,
                version_status=VersionStatus(version.status),
                sale_net=version.sale_net,
                updated_at=version.updated_at,
                approved_version_no=approved_no,
            )
            for budget, version, event, client_name, approved_no in page
        ],
        next_cursor=_encode_cursor(page[-1][1].updated_at, page[-1][0].id)
        if len(rows) > limit
        else None,
    )


def get_budget(db: AppSession, ctx: TenantContext, budget_id: UUID) -> BudgetOut:
    return budget_out(db, ctx, _budget(db, ctx, budget_id))


def export_version(
    db: AppSession, ctx: TenantContext, budget_id: UUID, version_no: int
) -> tuple[bytes, str]:
    """Excel de la versión con lo que el rol puede ver (queda en el audit: puede tener costos)."""
    budget = get_version(db, ctx, budget_id, version_no)
    _audit(
        db,
        ctx,
        "budget.exported",
        budget.id,
        after={"version_no": version_no, "costs": budget.version.costs is not None},
    )
    return version_xlsx(budget), f"presupuesto-{budget.number}-v{version_no}.xlsx"


def get_version(db: AppSession, ctx: TenantContext, budget_id: UUID, version_no: int) -> BudgetOut:
    budget = _budget(db, ctx, budget_id)
    version = db.execute(
        select(BudgetVersion).where(
            BudgetVersion.budget_id == budget.id, BudgetVersion.version_no == version_no
        )
    ).scalar_one_or_none()
    if version is None:
        raise not_found()
    return budget_out(db, ctx, budget, version)


# --- Alta ----------------------------------------------------------------------------------


def create_budget(db: AppSession, ctx: TenantContext, body: BudgetCreate) -> BudgetOut:
    if body.event is not None:
        event = create_event(db, ctx, body.event)
    elif body.event_id is not None:
        event = get_event(db, ctx, body.event_id)
    else:  # pragma: no cover - lo valida el schema
        raise AppError(422, "event_required", "Falta el evento")
    if not can_quote(event):
        raise AppError(409, "event_not_quotable", "El evento está cerrado, perdido o cancelado")
    budget = Budget(
        organization_id=ctx.organization_id,
        number=next_number(db, ctx.organization_id, "budget"),
        event_id=event.id,
        title=(body.title or event.name).strip(),
        currency=body.currency.value,
        created_by=ctx.user_id,
    )
    db.add(budget)
    db.flush()
    version = BudgetVersion(
        organization_id=ctx.organization_id,
        budget_id=budget.id,
        version_no=1,
        status=VersionStatus.DRAFT.value,
        context_snapshot=_context_json(pricing_context(db, ctx, event.client_id)),
        fx_snapshot=_fx_snapshot(db, ctx, budget.currency),
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
        pricing_engine_version="",
        created_by=ctx.user_id,
    )
    db.add(version)
    db.flush()
    db.add(
        BudgetSection(
            organization_id=ctx.organization_id,
            version_id=version.id,
            section_key=uuid4(),
            title_client=DEFAULT_SECTION_TITLE,
            sort=0,
        )
    )
    db.flush()
    _recalculate(db, budget, version)
    on_budget_created(db, ctx, event.id)
    _audit(
        db, ctx, "budget.created", budget.id, after={"number": budget.number, "event": event.name}
    )
    return budget_out(db, ctx, budget, version)


# --- Versión ---------------------------------------------------------------------------------


def update_version(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int, body: VersionUpdate
) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    fields = body.model_fields_set - {"currency", "refresh_fx"}
    if "markup_override" in fields and not ctx.can(Permission.MARKUP_OVERRIDE):
        raise AppError(403, "permission_denied", "No tenés permiso para pisar el markup")
    before = _jsonable({f: getattr(version, f) for f in fields})
    for field in fields:
        value = getattr(body, field)
        if (
            field
            in {
                "pricing_mode",
                "target_includes_iva",
                "global_discount_rate",
                "management_fee_rate",
            }
            and value is None
        ):
            continue
        setattr(version, field, value.value if field == "pricing_mode" else value)
    changes: dict[str, Any] = {}
    if body.currency is not None and body.currency != budget.currency:
        changes["currency"] = body.currency.value
        budget.currency = body.currency.value
        version.fx_snapshot = _fx_snapshot(db, ctx, budget.currency)
    elif body.refresh_fx:
        version.fx_snapshot = _fx_snapshot(db, ctx, budget.currency)
        changes["fx"] = version.fx_snapshot
    _recalculate(db, budget, version)
    old, new = diff(before, _jsonable({f: getattr(version, f) for f in fields}))
    if new or changes:
        action = (
            "budget.markup_overridden" if "markup_override" in new else "budget.version_updated"
        )
        _audit(db, ctx, action, budget.id, before=old, after={**new, **changes})
    return budget_out(db, ctx, budget, version)


def freeze(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int, body: FreezeIn
) -> BudgetOut:
    """ "Guardar versión": el borrador pasa a FROZEN y ya no cambia (I3)."""
    budget, version = _draft(db, ctx, budget_id, if_match)
    if not _lines(db, version.id):
        raise AppError(422, "budget_empty", "Agregá al menos una línea antes de guardar la versión")
    event = db.get(Event, budget.event_id)
    client = db.get(Client, event.client_id) if event else None
    version.header_snapshot = {
        "client": {
            "name": client.name if client else None,
            "legal_name": client.legal_name if client else None,
            "tax_id": client.tax_id if client else None,
        },
        "event": {
            "number": event.number if event else None,
            "name": event.name if event else None,
            "start_date": event.start_date.isoformat() if event and event.start_date else None,
            "end_date": event.end_date.isoformat() if event and event.end_date else None,
            "venue": event.venue if event else None,
            "city": event.city if event else None,
        },
    }
    version.change_note = (body.change_note or "").strip() or None
    version.frozen_at = utcnow()
    version.frozen_by = ctx.user_id
    version.status = VersionStatus.FROZEN.value
    version.lock_version += 1
    db.flush()
    _audit(db, ctx, "budget.version_frozen", budget.id, after={"version_no": version.version_no})
    return budget_out(db, ctx, budget, version)


def new_version(db: AppSession, ctx: TenantContext, budget_id: UUID) -> BudgetOut:
    """Nuevo borrador clonando la última versión, con las mismas claves de sección y línea.
    No actualiza costos ni reglas: eso es una acción explícita (§3.2)."""
    budget = _budget(db, ctx, budget_id)
    versions = _versions(db, budget.id)
    if any(v.status == VersionStatus.DRAFT for v in versions):
        raise AppError(409, "budget_draft_exists", "Ya hay un borrador en curso")
    source = versions[-1]
    draft = BudgetVersion(
        organization_id=ctx.organization_id,
        budget_id=budget.id,
        version_no=source.version_no + 1,
        status=VersionStatus.DRAFT.value,
        pricing_mode=source.pricing_mode,
        markup_override=source.markup_override,
        target_margin=source.target_margin,
        target_price=source.target_price,
        target_includes_iva=source.target_includes_iva,
        global_discount_rate=source.global_discount_rate,
        management_fee_rate=source.management_fee_rate,
        fx_snapshot=source.fx_snapshot,
        context_snapshot=source.context_snapshot,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
        pricing_engine_version=source.pricing_engine_version,
        cloned_from_version_id=source.id,
        created_by=ctx.user_id,
    )
    db.add(draft)
    db.flush()
    section_ids: dict[UUID, UUID] = {}
    for section in _sections(db, source.id):
        clone = BudgetSection(
            organization_id=ctx.organization_id,
            version_id=draft.id,
            section_key=section.section_key,
            title_client=section.title_client,
            sort=section.sort,
        )
        db.add(clone)
        db.flush()
        section_ids[section.id] = clone.id
    skip = {"id", "version_id", "section_id"}
    for line in _lines(db, source.id):
        values = {
            c.key: getattr(line, c.key) for c in BudgetLine.__table__.columns if c.key not in skip
        }
        db.add(BudgetLine(**values, version_id=draft.id, section_id=section_ids[line.section_id]))
    db.flush()
    _recalculate(db, budget, draft)
    _audit(
        db,
        ctx,
        "budget.version_created",
        budget.id,
        after={"version_no": draft.version_no, "from": source.version_no},
    )
    return budget_out(db, ctx, budget, draft)


def discard_draft(db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    if not any(v.status == VersionStatus.FROZEN for v in _versions(db, budget.id)):
        raise AppError(
            409, "budget_only_version", "Es la única versión: no se puede descartar el borrador"
        )
    _audit(db, ctx, "budget.draft_discarded", budget.id, before={"version_no": version.version_no})
    db.delete(version)
    db.flush()
    return budget_out(db, ctx, budget)


# --- Secciones -------------------------------------------------------------------------------


def add_section(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int, body: SectionIn
) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    sections = _sections(db, version.id)
    section = BudgetSection(
        organization_id=ctx.organization_id,
        version_id=version.id,
        section_key=uuid4(),
        title_client=body.title_client.strip(),
        sort=len(sections),
    )
    db.add(section)
    db.flush()
    _recalculate(db, budget, version)
    return budget_out(db, ctx, budget, version)


def update_section(
    db: AppSession,
    ctx: TenantContext,
    budget_id: UUID,
    section_id: UUID,
    *,
    if_match: int,
    body: SectionUpdate,
) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    section = _section(db, version, section_id)
    if body.title_client is not None:
        section.title_client = body.title_client.strip()
    if body.position is not None:
        _renumber(_sections(db, version.id), section, body.position)
    db.flush()
    _recalculate(db, budget, version)
    return budget_out(db, ctx, budget, version)


def delete_section(
    db: AppSession, ctx: TenantContext, budget_id: UUID, section_id: UUID, if_match: int
) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    section = _section(db, version, section_id)
    sections = _sections(db, version.id)
    if len(sections) == 1:
        raise AppError(409, "budget_last_section", "El presupuesto necesita al menos una sección")
    removed = db.execute(
        select(func.count()).select_from(BudgetLine).where(BudgetLine.section_id == section.id)
    ).scalar_one()
    db.execute(delete(BudgetLine).where(BudgetLine.section_id == section.id))
    db.delete(section)
    db.flush()
    for sort, item in enumerate(s for s in sections if s.id != section.id):
        item.sort = sort
    _recalculate(db, budget, version)
    _audit(
        db,
        ctx,
        "budget.section_removed",
        budget.id,
        before={"section": section.title_client, "lines": removed},
    )
    return budget_out(db, ctx, budget, version)


# --- Líneas --------------------------------------------------------------------------------


def _client_id(db: AppSession, budget: Budget) -> UUID:
    return db.execute(select(Event.client_id).where(Event.id == budget.event_id)).scalar_one()


def _event_days(db: AppSession, budget: Budget) -> int:
    return db.execute(select(Event.event_days).where(Event.id == budget.event_id)).scalar_one()


def add_line(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int, body: LineIn
) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    section = _section(db, version, body.section_id)
    custom_cost = (
        body.unit_cost_amount is not None
        or body.unit_cost_includes_iva is not None
        or body.cost_is_total
    )
    if custom_cost and not ctx.can(Permission.COST_VIEW):
        raise AppError(403, "permission_denied", "No tenés permiso para ver ni cargar costos")
    client_id = _client_id(db, budget)

    if body.product_id is not None:
        source = line_source(db, ctx, body.product_id, body.offer_id)
        product = source.product
        price = source.price
        resolved = resolve_line_markup(
            db, ctx, product=product, category_id=product.category_id, client_id=client_id
        )
        charge_mode = body.charge_mode or ChargeMode(product.charge_mode)
        line = BudgetLine(
            product_id=product.id,
            supplier_product_id=source.offer_id,
            supplier_id=source.supplier_id,
            price_history_id=price.id if price else None,
            category_id=product.category_id,
            name_internal=product.name,
            description_client=product.description_client,
            category_name=source.category_name,
            supplier_name=source.supplier_name,
            unit_code=source.unit_code,
            iva_rate=body.iva_rate if body.iva_rate is not None else source.iva_rate,
            unit_cost_amount=body.unit_cost_amount
            if body.unit_cost_amount is not None
            else (price.amount if price else Decimal(0)),
            unit_cost_includes_iva=body.unit_cost_includes_iva
            if body.unit_cost_includes_iva is not None
            else (price.amount_includes_iva if price else False),
            unit_cost_iva_rate=body.unit_cost_iva_rate
            if body.unit_cost_iva_rate is not None
            else (price.iva_rate if price else Decimal("0.21")),
            cost_as_of=None if custom_cost else (price.valid_from if price else None),
        )
        # Sin cantidad explícita, arranca en la mínima del producto (si tiene).
        quantity = (
            product.min_quantity
            if "quantity" not in body.model_fields_set and product.min_quantity
            else body.quantity
        )
    else:
        category_name = None
        category_iva = Decimal("0.21")
        if body.category_id is not None:
            category, category_iva = category_info(db, ctx, body.category_id)
            category_name = category.name
        resolved = resolve_line_markup(
            db, ctx, product=None, category_id=body.category_id, client_id=client_id
        )
        charge_mode = body.charge_mode or ChargeMode.FIXED
        line = BudgetLine(
            category_id=body.category_id,
            category_name=category_name,
            name_internal=(body.name or "").strip(),
            unit_code=body.unit_code or "u",
            iva_rate=body.iva_rate if body.iva_rate is not None else category_iva,
            unit_cost_amount=body.unit_cost_amount or Decimal(0),
            unit_cost_includes_iva=bool(body.unit_cost_includes_iva),
            unit_cost_iva_rate=body.unit_cost_iva_rate
            if body.unit_cost_iva_rate is not None
            else Decimal("0.21"),
        )
        quantity = body.quantity

    line.organization_id = ctx.organization_id
    line.version_id = version.id
    line.section_id = section.id
    line.line_key = uuid4()
    line.charge_mode = charge_mode.value
    line.quantity = quantity
    line.days = body.days or (_event_days(db, budget) if charge_mode is ChargeMode.PER_DAY else 1)
    line.unit_cost_currency = "ARS"
    line.cost_is_total = body.cost_is_total
    line.pricing_mode = LinePricingMode.MARKUP.value
    line.discount_rate = Decimal(0)
    line.is_locked = False
    line.show_on_proposal = True
    line.rule_markup = resolved.value
    line.rule_source = resolved.source.value
    line.rule_source_id = resolved.source_id
    line.sort = 0
    db.add(line)
    db.flush()
    siblings = list(
        db.execute(
            select(BudgetLine)
            .where(BudgetLine.section_id == section.id, BudgetLine.id != line.id)
            .order_by(BudgetLine.sort, BudgetLine.id)
        ).scalars()
    )
    _renumber([*siblings, line], line, body.position)
    db.flush()
    _recalculate(db, budget, version)
    _audit(
        db,
        ctx,
        "budget.line_added",
        budget.id,
        after={
            "line_key": str(line.line_key),
            "name": line.name_internal,
            "quantity": str(line.quantity),
        },
    )
    return budget_out(db, ctx, budget, version)


_COST_FIELDS = {
    "unit_cost_amount",
    "unit_cost_includes_iva",
    "unit_cost_iva_rate",
    "cost_is_total",
    "offer_id",
}
_MARGIN_FIELDS = {"markup_manual", "target_margin"}
_NOT_NULL = {
    "name_internal",
    "show_on_proposal",
    "quantity",
    "days",
    "charge_mode",
    "iva_rate",
    "unit_cost_amount",
    "unit_cost_includes_iva",
    "unit_cost_iva_rate",
    "cost_is_total",
    "pricing_mode",
    "discount_rate",
    "is_locked",
    "section_id",
}
_AUDITED = (
    "name_internal",
    "description_client",
    "quantity",
    "days",
    "unit_cost_amount",
    "unit_cost_includes_iva",
    "cost_is_total",
    "supplier_name",
    "client_price_label",
    "pricing_mode",
    "markup_manual",
    "target_margin",
    "target_price",
    "discount_rate",
    "is_locked",
    "section_id",
)


def _check_line_update(ctx: TenantContext, body: LineUpdate) -> None:
    fields = body.model_fields_set
    if fields & _COST_FIELDS and not ctx.can(Permission.COST_VIEW):
        raise AppError(403, "permission_denied", "No tenés permiso para ver ni cargar costos")
    if fields & _MARGIN_FIELDS and not ctx.can(Permission.MARGIN_VIEW):
        raise AppError(403, "permission_denied", "No tenés permiso para ver márgenes")
    if "markup_manual" in fields and not ctx.can(Permission.MARKUP_OVERRIDE):
        raise AppError(403, "permission_denied", "No tenés permiso para pisar el markup")
    for field in fields & _NOT_NULL:
        if getattr(body, field) is None:
            raise AppError(422, "field_required", f"{field} no puede quedar vacío")


def _switch_offer(db: AppSession, ctx: TenantContext, line: BudgetLine, offer_id: UUID) -> None:
    """Cambiar de proveedor: la línea toma la oferta y su costo vigente."""
    if line.product_id is None:
        raise AppError(422, "line_without_product", "Una línea libre no tiene proveedores")
    source = line_source(db, ctx, line.product_id, offer_id)
    price = source.price
    line.supplier_product_id = source.offer_id
    line.supplier_id = source.supplier_id
    line.supplier_name = source.supplier_name
    line.price_history_id = price.id if price else None
    line.unit_cost_amount = price.amount if price else Decimal(0)
    line.unit_cost_includes_iva = price.amount_includes_iva if price else False
    line.unit_cost_iva_rate = price.iva_rate if price else Decimal("0.21")
    line.cost_is_total = False  # el catálogo guarda costos unitarios
    line.cost_as_of = price.valid_from if price else None


def _move_line(
    db: AppSession,
    version: BudgetVersion,
    line: BudgetLine,
    section_id: UUID | None,
    position: int | None,
) -> None:
    if section_id is not None:
        line.section_id = _section(db, version, section_id).id
        db.flush()
    siblings = list(
        db.execute(
            select(BudgetLine)
            .where(BudgetLine.section_id == line.section_id, BudgetLine.id != line.id)
            .order_by(BudgetLine.sort, BudgetLine.id)
        ).scalars()
    )
    _renumber([*siblings, line], line, position)


def update_line(
    db: AppSession,
    ctx: TenantContext,
    budget_id: UUID,
    line_id: UUID,
    *,
    if_match: int,
    body: LineUpdate,
) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    line = _line(db, version, line_id)
    fields = set(body.model_fields_set)
    _check_line_update(ctx, body)
    before = _jsonable({f: getattr(line, f) for f in _AUDITED})

    if body.offer_id is not None:
        _switch_offer(db, ctx, line, body.offer_id)

    simple = fields - {"offer_id", "position", "section_id"}
    for field in simple:
        value = getattr(body, field)
        if isinstance(value, ChargeMode | LinePricingMode | ClientPriceLabel):
            value = value.value
        if field == "name_internal" and isinstance(value, str):
            value = value.strip()
        setattr(line, field, value)
    if fields & (_COST_FIELDS - {"offer_id"}):
        line.cost_as_of = None  # costo cargado a mano: ya no es el del catálogo
        line.price_history_id = None

    if "section_id" in fields or "position" in fields:
        _move_line(db, version, line, body.section_id, body.position)
    db.flush()
    _recalculate(db, budget, version)
    old, new = diff(before, _jsonable({f: getattr(line, f) for f in _AUDITED}))
    if new:
        _audit(
            db,
            ctx,
            "budget.line_updated",
            budget.id,
            before={"line_key": str(line.line_key), **old},
            after={"line_key": str(line.line_key), **new},
        )
    return budget_out(db, ctx, budget, version)


def delete_line(
    db: AppSession, ctx: TenantContext, budget_id: UUID, line_id: UUID, if_match: int
) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    line = _line(db, version, line_id)
    snapshot = {"line_key": str(line.line_key), "name": line.name_internal}
    section_id = line.section_id
    db.delete(line)
    db.flush()
    remaining = list(
        db.execute(
            select(BudgetLine).where(BudgetLine.section_id == section_id).order_by(BudgetLine.sort)
        ).scalars()
    )
    for sort, item in enumerate(remaining):
        item.sort = sort
    _recalculate(db, budget, version)
    _audit(db, ctx, "budget.line_removed", budget.id, before=snapshot)
    return budget_out(db, ctx, budget, version)


# --- Actualizar costos y re-aplicar reglas (B-08) --------------------------------------------
# Acciones explícitas con vista previa: nada del borrador cambia "por debajo" (P3).


def _draft_readonly(
    db: AppSession, ctx: TenantContext, budget_id: UUID
) -> tuple[Budget, BudgetVersion]:
    budget = _budget(db, ctx, budget_id)
    version = db.execute(
        select(BudgetVersion).where(
            BudgetVersion.budget_id == budget.id, BudgetVersion.status == VersionStatus.DRAFT
        )
    ).scalar_one_or_none()
    if version is None:
        raise AppError(409, "budget_no_draft", "Este presupuesto no tiene un borrador para editar")
    return budget, version


def _totals_delta(ctx: TenantContext, version: BudgetVersion, after: VersionPriced) -> TotalsDelta:
    margins = ctx.can(Permission.MARGIN_VIEW)
    return TotalsDelta(
        sale_net_before=version.sale_net,
        sale_net_after=after.sale_net,
        profit_before=version.profit if margins else None,
        profit_after=after.profit if margins else None,
        margin_net_before=version.margin_net if margins else None,
        margin_net_after=after.margin_net if margins else None,
    )


def _cost_changes(
    db: AppSession, ctx: TenantContext, lines: list[BudgetLine]
) -> list[tuple[BudgetLine, Any]]:
    """Líneas del catálogo cuyo costo vigente hoy no es el que tiene la línea."""
    offer_ids = [line.supplier_product_id for line in lines if line.supplier_product_id]
    prices = current_prices(db, ctx, [i for i in offer_ids if i is not None])
    changes = []
    for line in lines:
        price = prices.get(line.supplier_product_id) if line.supplier_product_id else None
        if price is not None and price.id != line.price_history_id:
            changes.append((line, price))
    return changes


def _cost_override(price: Any) -> dict[str, Any]:
    return {
        "unit_cost": price.amount,
        "cost_includes_iva": price.amount_includes_iva,
        "cost_iva_rate": price.iva_rate,
    }


def preview_refresh_costs(db: AppSession, ctx: TenantContext, budget_id: UUID) -> CostsPreview:
    _, version = _draft_readonly(db, ctx, budget_id)
    lines = _lines(db, version.id)
    changes = _cost_changes(db, ctx, lines)
    _, _, after = _price(
        version, lines, overrides={line.id: _cost_override(price) for line, price in changes}
    )
    return CostsPreview(
        changes=[
            CostChange(
                line_id=line.id,
                name=line.name_internal,
                supplier_name=line.supplier_name,
                old_unit_cost=line.unit_cost_amount,
                new_unit_cost=price.amount,
                old_as_of=line.cost_as_of,
                new_as_of=price.valid_from,
                amount_changed=(
                    price.amount != line.unit_cost_amount
                    or price.amount_includes_iva != line.unit_cost_includes_iva
                    or price.iva_rate != line.unit_cost_iva_rate
                ),
            )
            for line, price in changes
        ],
        totals=_totals_delta(ctx, version, after),
    )


def _apply_costs(changes: list[tuple[BudgetLine, Any]]) -> None:
    for line, price in changes:
        line.unit_cost_amount = price.amount
        line.unit_cost_includes_iva = price.amount_includes_iva
        line.unit_cost_iva_rate = price.iva_rate
        line.cost_is_total = False
        line.cost_as_of = price.valid_from
        line.price_history_id = price.id


def refresh_costs(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int, body: RefreshCostsIn
) -> BudgetOut:
    budget, version = _draft(db, ctx, budget_id, if_match)
    changes = _cost_changes(db, ctx, _lines(db, version.id))
    if body.line_ids is not None:
        chosen = set(body.line_ids)
        changes = [(line, price) for line, price in changes if line.id in chosen]
    _apply_costs(changes)
    db.flush()
    _recalculate(db, budget, version)
    _audit(
        db,
        ctx,
        "budget.costs_refreshed",
        budget.id,
        after={"lines": [str(line.line_key) for line, _ in changes]},
    )
    return budget_out(db, ctx, budget, version)


def _rule_changes(
    db: AppSession, ctx: TenantContext, budget: Budget, lines: list[BudgetLine]
) -> list[tuple[BudgetLine, ResolvedMarkup]]:
    client_id = _client_id(db, budget)
    products = {
        p.id: p
        for p in db.execute(
            select(Product).where(Product.id.in_([ln.product_id for ln in lines if ln.product_id]))
        ).scalars()
    }
    changes = []
    for line in lines:
        product = products.get(line.product_id) if line.product_id else None
        resolved = resolve_line_markup(
            db, ctx, product=product, category_id=line.category_id, client_id=client_id
        )
        if resolved.value != line.rule_markup or resolved.source.value != line.rule_source:
            changes.append((line, resolved))
    return changes


def _context_now(db: AppSession, ctx: TenantContext, budget: Budget) -> dict[str, Any]:
    return _context_json(pricing_context(db, ctx, _client_id(db, budget)))


def preview_reapply_rules(db: AppSession, ctx: TenantContext, budget_id: UUID) -> RulesPreview:
    budget, version = _draft_readonly(db, ctx, budget_id)
    lines = _lines(db, version.id)
    changes = _rule_changes(db, ctx, budget, lines)
    context = _context_now(db, ctx, budget)
    _, _, after = _price(
        version,
        lines,
        context=context,
        overrides={line.id: {"resolved": resolved} for line, resolved in changes},
    )
    return RulesPreview(
        changes=[
            RuleChange(
                line_id=line.id,
                name=line.name_internal,
                old_markup=line.rule_markup,
                new_markup=resolved.value.quantize(UNIT),
                old_source=MarkupSource(line.rule_source),
                new_source=resolved.source,
                has_manual_markup=line.markup_manual is not None,
            )
            for line, resolved in changes
        ],
        charges_before=[ChargeRate(**c) for c in version.context_snapshot["sale_charges"]],
        charges_after=[ChargeRate(**c) for c in context["sale_charges"]],
        totals=_totals_delta(ctx, version, after),
    )


def _apply_rules(changes: list[tuple[BudgetLine, ResolvedMarkup]]) -> None:
    for line, resolved in changes:
        line.rule_markup = resolved.value.quantize(UNIT)
        line.rule_source = resolved.source.value
        line.rule_source_id = resolved.source_id


def reapply_rules(db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int) -> BudgetOut:
    """Toma las reglas de markup, los cargos sobre la venta y el redondeo vigentes hoy."""
    budget, version = _draft(db, ctx, budget_id, if_match)
    changes = _rule_changes(db, ctx, budget, _lines(db, version.id))
    _apply_rules(changes)
    version.context_snapshot = _context_now(db, ctx, budget)
    db.flush()
    _recalculate(db, budget, version)
    _audit(
        db,
        ctx,
        "budget.rules_reapplied",
        budget.id,
        after={"lines": [str(line.line_key) for line, _ in changes]},
    )
    return budget_out(db, ctx, budget, version)


# --- Duplicar (B-07) -------------------------------------------------------------------------


def duplicate(
    db: AppSession, ctx: TenantContext, budget_id: UUID, body: DuplicateIn
) -> DuplicateOut:
    """Copia la última versión a otro evento con los costos y reglas de hoy. Los ítems por día
    que usaban los días del evento original pasan a los del nuevo."""
    source_budget = _budget(db, ctx, budget_id)
    source = _versions(db, source_budget.id)[-1]
    source_days = _event_days(db, source_budget)
    created = create_budget(
        db,
        ctx,
        BudgetCreate(
            event_id=body.event_id,
            event=body.event,
            title=body.title or source_budget.title,
            currency=BudgetCurrency(source_budget.currency),
        ),
    )
    budget = _budget(db, ctx, created.id)
    version = db.execute(
        select(BudgetVersion).where(BudgetVersion.budget_id == budget.id)
    ).scalar_one()
    for field in (
        "pricing_mode",
        "markup_override",
        "target_margin",
        "target_price",
        "target_includes_iva",
        "global_discount_rate",
        "management_fee_rate",
    ):
        setattr(version, field, getattr(source, field))
    db.execute(delete(BudgetSection).where(BudgetSection.version_id == version.id))
    new_days = _event_days(db, budget)
    section_ids: dict[UUID, UUID] = {}
    for section in _sections(db, source.id):
        clone = BudgetSection(
            organization_id=ctx.organization_id,
            version_id=version.id,
            section_key=uuid4(),
            title_client=section.title_client,
            sort=section.sort,
        )
        db.add(clone)
        db.flush()
        section_ids[section.id] = clone.id
    skip = {"id", "version_id", "section_id", "line_key"}
    for line in _lines(db, source.id):
        values = {
            c.key: getattr(line, c.key) for c in BudgetLine.__table__.columns if c.key not in skip
        }
        if line.charge_mode == ChargeMode.PER_DAY and line.days == source_days:
            values["days"] = new_days
        db.add(
            BudgetLine(
                **values,
                version_id=version.id,
                section_id=section_ids[line.section_id],
                line_key=uuid4(),
            )
        )
    db.flush()
    lines = _lines(db, version.id)
    cost_changes = _cost_changes(db, ctx, lines)
    rule_changes = _rule_changes(db, ctx, budget, lines)
    _apply_costs(cost_changes)
    _apply_rules(rule_changes)
    db.flush()
    _recalculate(db, budget, version)
    _audit(
        db,
        ctx,
        "budget.duplicated",
        budget.id,
        after={"from_budget": source_budget.number, "from_version": source.version_no},
    )
    return DuplicateOut(
        budget=budget_out(db, ctx, budget, version),
        costs_changed=len(cost_changes),
        rules_changed=len(rule_changes),
    )


# --- Comparar versiones (§8) -----------------------------------------------------------------

# Campos que cuentan como modificación, con el permiso que hace falta para verlos.
_DIFF_FIELDS: tuple[tuple[str, Permission | None], ...] = (
    ("name_internal", None),
    ("description_client", None),
    ("quantity", None),
    ("days", None),
    ("supplier_name", None),
    ("unit_cost_amount", Permission.COST_VIEW),
    ("unit_cost_includes_iva", Permission.COST_VIEW),
    ("pricing_mode", None),
    ("markup_applied", Permission.MARGIN_VIEW),
    ("discount_rate", None),
    ("sale_total", None),
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return format(normalized, "f")
    return str(value)


def _version_by_no(db: AppSession, budget: Budget, version_no: int) -> BudgetVersion:
    version = db.execute(
        select(BudgetVersion).where(
            BudgetVersion.budget_id == budget.id, BudgetVersion.version_no == version_no
        )
    ).scalar_one_or_none()
    if version is None:
        raise not_found()
    return version


def compare_versions(
    db: AppSession, ctx: TenantContext, budget_id: UUID, before_no: int, after_no: int
) -> CompareOut:
    budget = _budget(db, ctx, budget_id)
    before = _version_by_no(db, budget, before_no)
    after = _version_by_no(db, budget, after_no)
    visible = [field for field, perm in _DIFF_FIELDS if perm is None or ctx.can(perm)]
    titles = {
        s.id: (s.section_key, s.title_client)
        for s in [*_sections(db, before.id), *_sections(db, after.id)]
    }
    old = {line.line_key: line for line in _lines(db, before.id)}
    new = {line.line_key: line for line in _lines(db, after.id)}
    old_order = {key: i for i, key in enumerate(old)}
    new_order = {key: i for i, key in enumerate(new)}

    diffs: list[LineDiff] = []
    reordered = 0
    for key in [*new, *(k for k in old if k not in new)]:
        a, b = old.get(key), new.get(key)
        if a is None or b is None:
            line = cast(BudgetLine, b or a)
            diffs.append(
                LineDiff(
                    line_key=key,
                    name=line.name_internal,
                    kind=DiffKind.ADDED if a is None else DiffKind.REMOVED,
                    section_before=titles[a.section_id][1] if a else None,
                    section_after=titles[b.section_id][1] if b else None,
                    sale_before=a.sale_total if a else None,
                    sale_after=b.sale_total if b else None,
                    changes=[],
                )
            )
            continue
        changes = [
            FieldChange(field=f, before=_text(getattr(a, f)), after=_text(getattr(b, f)))
            for f in visible
            if _text(getattr(a, f)) != _text(getattr(b, f))
        ]
        section_a, section_b = titles[a.section_id], titles[b.section_id]
        if section_a[0] != section_b[0]:
            changes.append(FieldChange(field="section", before=section_a[1], after=section_b[1]))
        if changes:
            diffs.append(
                LineDiff(
                    line_key=key,
                    name=b.name_internal,
                    kind=DiffKind.MODIFIED,
                    section_before=section_a[1],
                    section_after=section_b[1],
                    sale_before=a.sale_total,
                    sale_after=b.sale_total,
                    changes=changes,
                )
            )
        elif old_order[key] != new_order[key]:
            reordered += 1

    costs = ctx.can(Permission.COST_VIEW)
    margins = ctx.can(Permission.MARGIN_VIEW)
    delta = (
        ((after.margin_net - before.margin_net) * 100).quantize(Decimal("0.01"))
        if margins and after.margin_net is not None and before.margin_net is not None
        else None
    )
    return CompareOut(
        version_before=before.version_no,
        version_after=after.version_no,
        added=sum(d.kind is DiffKind.ADDED for d in diffs),
        removed=sum(d.kind is DiffKind.REMOVED for d in diffs),
        modified=sum(d.kind is DiffKind.MODIFIED for d in diffs),
        reordered=reordered,
        lines=diffs,
        sale_net_before=before.sale_net,
        sale_net_after=after.sale_net,
        total_before=before.total,
        total_after=after.total,
        cost_before=before.cost_direct if costs else None,
        cost_after=after.cost_direct if costs else None,
        profit_before=before.profit if margins else None,
        profit_after=after.profit if margins else None,
        margin_net_before=before.margin_net if margins else None,
        margin_net_after=after.margin_net if margins else None,
        margin_delta_points=delta,
    )


def freeze_for_proposal(
    db: AppSession, ctx: TenantContext, budget_id: UUID, if_match: int | None
) -> int:
    """La versión a enviar: congela el borrador (si hay, con su lock) o toma la última guardada."""
    budget = _budget(db, ctx, budget_id)
    has_draft = any(v.status == VersionStatus.DRAFT for v in _versions(db, budget.id))
    if has_draft:
        if if_match is None:
            raise AppError(428, "if_match_required", "Falta If-Match para congelar el borrador")
        return freeze(
            db, ctx, budget.id, if_match, FreezeIn(change_note="Enviada al cliente")
        ).version.version_no
    return _versions(db, budget.id)[-1].version_no
