"""Valores iniciales de una organización nueva (catálogo base y reglas de pricing)."""

from uuid import UUID

from app.core.db import AppSession
from app.modules.catalog import seed_catalog_defaults
from app.modules.pricing import seed_pricing_defaults


def provision_organization(db: AppSession, organization_id: UUID) -> None:
    """Requiere contexto de la organización y que la fila de la organización ya exista."""
    seed_catalog_defaults(db, organization_id)
    seed_pricing_defaults(db, organization_id)
