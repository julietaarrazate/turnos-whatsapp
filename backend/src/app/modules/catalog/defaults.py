"""Valores iniciales del catálogo para una organización nueva (la migración 0004 hace lo
mismo para las que ya existían)."""

from uuid import UUID

from app.core.db import AppSession
from app.modules.catalog.models import Category, Supplier, Unit

DEFAULT_UNITS = [
    ("u", "Unidad", False),
    ("m2", "Metro cuadrado", True),
    ("ml", "Metro lineal", True),
    ("dia", "Día", False),
    ("h", "Hora", True),
    ("pers", "Persona", False),
    ("viaje", "Viaje", False),
    ("gl", "Global", False),
]

DEFAULT_CATEGORIES = [
    "Gráfica",
    "Estructura",
    "Iluminación",
    "Mobiliario",
    "Técnica (audio y video)",
    "Personal",
    "Armado y desarme",
    "Transporte",
    "Catering",
    "Terceros",
]

INTERNAL_SUPPLIER_NAME = "Equipo propio"


def seed_catalog_defaults(db: AppSession, organization_id: UUID) -> None:
    """Requiere contexto de la organización."""
    for code, name, decimals in DEFAULT_UNITS:
        db.add(
            Unit(organization_id=organization_id, code=code, name=name, allows_decimals=decimals)
        )
    for sort, name in enumerate(DEFAULT_CATEGORIES, start=1):
        db.add(Category(organization_id=organization_id, name=name, sort=sort))
    db.add(Supplier(organization_id=organization_id, name=INTERNAL_SUPPLIER_NAME, is_internal=True))
    db.flush()
