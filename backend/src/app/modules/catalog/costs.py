"""Costo vigente y antigüedad (DOMAIN_MODEL §2.3: price_history append-only)."""

from collections.abc import Iterable
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on

from app.core.db import AppSession
from app.modules.catalog.models import PriceHistory
from app.modules.catalog.schemas import CostOut

DEFAULT_STALENESS_DAYS = 30
STALENESS_SETTING = "price_staleness_days"
_AR = ZoneInfo("America/Argentina/Buenos_Aires")


def today_ar() -> date:
    return datetime.now(_AR).date()


def staleness_days(org_settings: dict[str, object]) -> int:
    value = org_settings.get(STALENESS_SETTING)
    return value if isinstance(value, int) and value > 0 else DEFAULT_STALENESS_DAYS


def cost_out(price: PriceHistory, today: date, stale_after: int) -> CostOut:
    days_old = max((today - price.valid_from).days, 0)
    return CostOut(
        amount=price.amount,
        currency=price.currency,
        includes_iva=price.amount_includes_iva,
        iva_rate=price.iva_rate,
        valid_from=price.valid_from,
        days_old=days_old,
        stale=days_old > stale_after,
    )


def current_and_upcoming(
    db: AppSession, offer_ids: Iterable[UUID], today: date
) -> tuple[dict[UUID, PriceHistory], dict[UUID, PriceHistory]]:
    """Para cada oferta: el costo vigente hoy y el próximo con fecha futura (si hay)."""
    ids = list(offer_ids)
    if not ids:
        return {}, {}
    current = db.execute(
        select(PriceHistory)
        .where(PriceHistory.supplier_product_id.in_(ids), PriceHistory.valid_from <= today)
        .order_by(
            PriceHistory.supplier_product_id,
            PriceHistory.valid_from.desc(),
            PriceHistory.created_at.desc(),
            PriceHistory.id.desc(),
        )
        .ext(distinct_on(PriceHistory.supplier_product_id))
    ).scalars()
    upcoming = db.execute(
        select(PriceHistory)
        .where(PriceHistory.supplier_product_id.in_(ids), PriceHistory.valid_from > today)
        .order_by(
            PriceHistory.supplier_product_id,
            PriceHistory.valid_from.asc(),
            PriceHistory.created_at.desc(),
        )
        .ext(distinct_on(PriceHistory.supplier_product_id))
    ).scalars()
    return (
        {p.supplier_product_id: p for p in current},
        {p.supplier_product_id: p for p in upcoming},
    )
