"""Ficha del lugar: lo que hay que saber de un predio para montar, cargada una vez y reusada.

Va atada al nombre del lugar del evento (sin acentos ni mayúsculas: "Costa Salguero" y
"costa salguero" son el mismo). No hace falta elegir nada de una lista.
"""

from uuid import UUID

from sqlalchemy import func, select

from app.core.db import AppSession
from app.core.errors import AppError
from app.core.security import utcnow
from app.modules.auth import TenantContext
from app.modules.events import Event, get_event
from app.modules.identity import User
from app.modules.production.files import _can_edit, normalize
from app.modules.production.models import VenueSheet
from app.modules.production.schemas import EventVenueOut, VenueSheetIn, VenueSheetOut
from app.modules.production.service import _audit

_FIELDS = ("address", "maps_url", "load_in", "measures", "rules", "contacts", "notes")


def _sheet(db: AppSession, organization_id: UUID, venue: str) -> VenueSheet | None:
    return db.execute(
        select(VenueSheet).where(
            VenueSheet.organization_id == organization_id,
            VenueSheet.name_key == normalize(venue),
        )
    ).scalar_one_or_none()


def _out(db: AppSession, sheet: VenueSheet) -> VenueSheetOut:
    author = db.execute(select(User.name).where(User.id == sheet.updated_by)).scalar_one()
    return VenueSheetOut(
        id=sheet.id,
        name=sheet.name,
        updated_by_name=author,
        updated_at=sheet.updated_at,
        **{field: getattr(sheet, field) for field in _FIELDS},
    )


def for_event(db: AppSession, ctx: TenantContext, event_id: UUID) -> EventVenueOut:
    event = get_event(db, ctx, event_id)
    venue = (event.venue or "").strip() or None
    if venue is None:
        return EventVenueOut(venue=None, sheet=None, other_events=0, can_edit=_can_edit(ctx))
    sheet = _sheet(db, ctx.organization_id, venue)
    others = db.execute(
        select(func.count()).where(
            Event.organization_id == ctx.organization_id,
            Event.id != event.id,
            Event.deleted_at.is_(None),
            func.lower(func.trim(Event.venue)) == venue.lower(),
        )
    ).scalar_one()
    return EventVenueOut(
        venue=venue,
        sheet=_out(db, sheet) if sheet else None,
        other_events=others,
        can_edit=_can_edit(ctx),
    )


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def save(db: AppSession, ctx: TenantContext, event_id: UUID, body: VenueSheetIn) -> EventVenueOut:
    """Crea o actualiza la ficha del lugar del evento (la ven todos los eventos de ese lugar)."""
    if not _can_edit(ctx):
        raise AppError(403, "files_read_only", "Tu rol puede ver la ficha, no cambiarla")
    event = get_event(db, ctx, event_id)
    venue = (event.venue or "").strip()
    if not venue:
        raise AppError(422, "venue_missing", "Primero cargá el lugar del evento")
    maps_url = _clean(body.maps_url)
    if maps_url and not maps_url.startswith("https://"):
        raise AppError(422, "url_invalid", "El link del mapa tiene que empezar con https://")
    sheet = _sheet(db, ctx.organization_id, venue)
    if sheet is None:
        sheet = VenueSheet(
            organization_id=ctx.organization_id, name=venue, name_key=normalize(venue)
        )
        db.add(sheet)
    for field in _FIELDS:
        setattr(sheet, field, _clean(getattr(body, field)))
    sheet.maps_url = maps_url
    sheet.updated_by = ctx.user_id
    sheet.updated_at = utcnow()
    db.flush()
    _audit(db, ctx, "venue.sheet_updated", event.id, after={"venue": venue})
    return for_event(db, ctx, event_id)
