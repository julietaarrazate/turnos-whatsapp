"""Lo que el cliente ve de una versión congelada (ARCHITECTURE §8.4).

Se arma por **lista blanca**: cada clave se escribe acá a mano. Nunca se serializa un modelo
interno "sacando" campos. Un test recorre el JSON y falla si aparece una clave prohibida
(costo, markup, margen, ganancia, proveedor, notas internas) o un valor igual a un costo.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.domain.pricing import ChargeMode, allocate
from app.modules.auth import TenantContext
from app.modules.budgets.models import (
    Budget,
    BudgetCurrency,
    BudgetLine,
    BudgetSection,
    BudgetVersion,
    VersionStatus,
)
from app.modules.catalog import today_ar
from app.modules.clients import Client
from app.modules.events import Event
from app.modules.identity import Organization
from app.modules.pricing import settings_from

CENT = Decimal("0.01")
PUBLIC_SCHEMA_VERSION = 1


class DisplayMode(StrEnum):
    DETAILED = "DETAILED"  # importes por ítem
    BY_SECTION = "BY_SECTION"  # descripciones y totales por sección
    TOTAL_ONLY = "TOTAL_ONLY"  # descripciones y total


class IvaDisplay(StrEnum):
    PLUS_IVA = "PLUS_IVA"
    IVA_INCLUDED = "IVA_INCLUDED"


@dataclass(frozen=True)
class SendableVersion:
    budget_id: UUID
    budget_number: int
    version_id: UUID
    version_no: int
    event_id: UUID
    client_id: UUID
    currency: str


def sendable_version(
    db: AppSession, ctx: TenantContext, budget_id: UUID, version_no: int
) -> SendableVersion:
    """Una versión congelada del presupuesto (I5: las propuestas solo apuntan a FROZEN)."""
    row = db.execute(
        select(Budget, BudgetVersion, Event)
        .join(BudgetVersion, BudgetVersion.budget_id == Budget.id)
        .join(Event, Event.id == Budget.event_id)
        .where(
            Budget.id == budget_id,
            Budget.organization_id == ctx.organization_id,
            BudgetVersion.version_no == version_no,
        )
    ).one_or_none()
    if row is None:
        raise not_found()
    budget, version, event = row
    if version.status != VersionStatus.FROZEN:
        raise AppError(409, "version_not_frozen", "Solo se envían versiones guardadas")
    return SendableVersion(
        budget_id=budget.id,
        budget_number=budget.number,
        version_id=version.id,
        version_no=version.version_no,
        event_id=event.id,
        client_id=event.client_id,
        currency=budget.currency,
    )


def budget_event_id(db: AppSession, organization_id: UUID, budget_id: UUID) -> UUID:
    """El evento del presupuesto (para propuestas, también desde el link público)."""
    event_id = db.execute(
        select(Budget.event_id).where(
            Budget.id == budget_id, Budget.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if event_id is None:
        raise not_found()
    return event_id


@dataclass(frozen=True)
class BaselineLine:
    """Una línea de la versión aceptada, para producción (lista de contratación y tareas)."""

    line_key: UUID
    name: str
    supplier_id: UUID | None
    supplier_name: str | None
    category_id: UUID | None
    category_name: str | None
    quantity: Decimal
    unit_code: str
    days: int
    cost_total: Decimal
    section_title: str = ""  # el rubro, para elegir la línea al cargar un gasto


@dataclass(frozen=True)
class VersionTotals:
    """Los totales de una versión congelada (la estimación con la que se vendió el evento)."""

    sale_net: Decimal
    cost_direct: Decimal
    sale_charges: Decimal
    profit: Decimal
    margin_net: Decimal | None


def version_totals(db: AppSession, organization_id: UUID, version_id: UUID) -> VersionTotals | None:
    version = db.execute(
        select(BudgetVersion).where(
            BudgetVersion.id == version_id,
            BudgetVersion.organization_id == organization_id,
            BudgetVersion.status == VersionStatus.FROZEN,
        )
    ).scalar_one_or_none()
    if version is None:
        return None
    return VersionTotals(
        sale_net=version.sale_net,
        cost_direct=version.cost_direct,
        sale_charges=version.sale_charges,
        profit=version.profit,
        margin_net=version.margin_net,
    )


def versions_totals(
    db: AppSession, organization_id: UUID, version_ids: list[UUID]
) -> dict[UUID, VersionTotals]:
    """Lo mismo que `version_totals` para varias versiones congeladas (reportes)."""
    if not version_ids:
        return {}
    rows = db.execute(
        select(BudgetVersion).where(
            BudgetVersion.id.in_(version_ids),
            BudgetVersion.organization_id == organization_id,
            BudgetVersion.status == VersionStatus.FROZEN,
        )
    ).scalars()
    return {
        v.id: VersionTotals(
            sale_net=v.sale_net,
            cost_direct=v.cost_direct,
            sale_charges=v.sale_charges,
            profit=v.profit,
            margin_net=v.margin_net,
        )
        for v in rows
    }


def baseline_lines(db: AppSession, organization_id: UUID, version_id: UUID) -> list[BaselineLine]:
    """Las líneas de una versión congelada, en el orden del presupuesto."""
    rows = db.execute(
        select(BudgetLine, BudgetSection.title_client)
        .join(BudgetSection, BudgetSection.id == BudgetLine.section_id)
        .join(BudgetVersion, BudgetVersion.id == BudgetLine.version_id)
        .where(
            BudgetLine.version_id == version_id,
            BudgetLine.organization_id == organization_id,
            BudgetVersion.status == VersionStatus.FROZEN,
        )
        .order_by(BudgetSection.sort, BudgetLine.sort)
    ).all()
    return [
        BaselineLine(
            line_key=line.line_key,
            name=line.name_internal,
            supplier_id=line.supplier_id,
            supplier_name=line.supplier_name,
            category_id=line.category_id,
            category_name=line.category_name,
            quantity=line.quantity,
            unit_code=line.unit_code,
            days=line.days,
            cost_total=line.cost_total,
            section_title=section_title,
        )
        for line, section_title in rows
    ]


def _money(value: Decimal) -> str:
    return str(value.quantize(CENT))


def _quantity(value: Decimal) -> str:
    return format(value.normalize(), "f")


def public_snapshot(
    db: AppSession,
    version_id: UUID,
    *,
    display_mode: DisplayMode,
    iva_display: IvaDisplay,
) -> dict[str, Any]:
    """Importes, textos y totales que ve el cliente. Todo lo que no está acá, no viaja."""
    version = db.get(BudgetVersion, version_id)
    if version is None or version.status != VersionStatus.FROZEN:  # pragma: no cover - I5
        raise not_found()
    budget = db.get(Budget, version.budget_id)
    if budget is None:  # pragma: no cover - FK
        raise not_found()
    sections = list(
        db.execute(
            select(BudgetSection)
            .where(BudgetSection.version_id == version.id)
            .order_by(BudgetSection.sort, BudgetSection.id)
        ).scalars()
    )
    lines = list(
        db.execute(
            select(BudgetLine)
            .join(BudgetSection, BudgetSection.id == BudgetLine.section_id)
            .where(BudgetLine.version_id == version.id)
            .order_by(BudgetSection.sort, BudgetSection.id, BudgetLine.sort, BudgetLine.id)
        ).scalars()
    )

    # Importes por línea en la moneda de la propuesta (sin IVA, antes del descuento global).
    usd = budget.currency != BudgetCurrency.ARS and version.presentation is not None
    if usd and version.presentation is not None:
        shown = version.presentation
        amounts = {line.id: Decimal(shown["lines"][str(line.id)]) for line in lines}
        subtotal, discount = Decimal(shown["subtotal"]), Decimal(shown["global_discount"])
        fee = Decimal(shown.get("management_fee", "0"))
        net, iva, total = Decimal(shown["net"]), Decimal(shown["iva"]), Decimal(shown["total"])
    else:
        amounts = {line.id: line.sale_total for line in lines}
        subtotal, discount = version.sale_subtotal, version.global_discount
        fee = version.management_fee
        net, iva, total = version.sale_net, version.iva, version.total

    if iva_display is IvaDisplay.IVA_INCLUDED:
        # Cada línea (y el fee de gestión) con su parte del descuento y del IVA, repartido para
        # que sume el total exacto.
        weights = [
            amounts[line.id] * (subtotal - discount) / subtotal if subtotal else Decimal(0)
            for line in lines
        ]
        shares = allocate(total, [*weights, fee] if fee else weights, CENT)
        amounts = dict(zip([line.id for line in lines], shares[: len(lines)], strict=True))
        fee = shares[-1] if fee else fee

    detailed = display_mode is DisplayMode.DETAILED
    by_section = display_mode is not DisplayMode.TOTAL_ONLY
    public_sections = []
    for section in sections:
        section_lines = [line for line in lines if line.section_id == section.id]
        items = []
        for line in section_lines:
            if not line.show_on_proposal:
                continue  # su importe igual suma en la sección
            units = line.quantity * (line.days if line.charge_mode == ChargeMode.PER_DAY else 1)
            amount = amounts[line.id]
            unit_price = (amount / units) if units else None
            exact = unit_price is not None and unit_price == unit_price.quantize(CENT)
            # "Bonificado" / "A definir": el cliente ve la etiqueta, no un importe.
            label = line.client_price_label
            priced = detailed and label is None
            items.append(
                {
                    "description": line.description_client or line.name_internal,
                    "quantity": _quantity(line.quantity),
                    "unit": line.unit_code,
                    "days": line.days if line.charge_mode == ChargeMode.PER_DAY else None,
                    "unit_price": _money(unit_price)
                    if priced and exact and unit_price is not None
                    else None,
                    "amount": _money(amount) if priced else None,
                    "price_label": label,
                }
            )
        public_sections.append(
            {
                "title": section.title_client,
                "items": items,
                "total": _money(sum((amounts[ln.id] for ln in section_lines), Decimal(0)))
                if by_section
                else None,
            }
        )

    event = db.get(Event, budget.event_id)
    client = db.get(Client, event.client_id) if event else None
    totals: dict[str, Any] = {"total": _money(total)}
    if fee:
        totals |= {
            "management_fee": _money(fee),
            "management_fee_rate": f"{version.management_fee_rate.normalize():f}",
        }
    if iva_display is IvaDisplay.PLUS_IVA:
        totals |= {
            "subtotal": _money(subtotal),
            "global_discount": _money(discount) if discount else None,
            "net": _money(net),
            "iva": _money(iva),
        }
    else:
        totals |= {"iva_included": _money(iva)}
    return {
        "schema_version": PUBLIC_SCHEMA_VERSION,
        "budget_number": budget.number,
        "version_no": version.version_no,
        "title": budget.title,
        "currency": budget.currency,
        "display_mode": display_mode.value,
        "iva_display": iva_display.value,
        "client": {"name": client.name if client else None},
        "event": {
            "name": event.name if event else None,
            "start_date": event.start_date.isoformat() if event and event.start_date else None,
            "end_date": event.end_date.isoformat() if event and event.end_date else None,
            "venue": event.venue if event else None,
            "city": event.city if event else None,
        },
        "sections": public_sections,
        "totals": totals,
    }


def stale_cost_count(db: AppSession, ctx: TenantContext, *, own_only: bool) -> int:
    """Líneas de borradores abiertos con un costo del catálogo más viejo que el umbral de la
    organización ("costos desactualizados", PRODUCT_SPEC §4.1)."""
    org = db.get(Organization, ctx.organization_id)
    stale_after = settings_from(org.settings if org else {}).price_staleness_days
    query = (
        select(func.count())
        .select_from(BudgetLine)
        .join(BudgetVersion, BudgetVersion.id == BudgetLine.version_id)
        .join(Budget, Budget.id == BudgetVersion.budget_id)
        .where(
            BudgetLine.organization_id == ctx.organization_id,
            BudgetVersion.status == VersionStatus.DRAFT,
            BudgetLine.supplier_product_id.is_not(None),
            BudgetLine.cost_as_of < today_ar() - timedelta(days=stale_after),
        )
    )
    if own_only:
        query = query.where(Budget.created_by == ctx.user_id)
    return db.execute(query).scalar_one()
