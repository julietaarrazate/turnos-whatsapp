"""Catálogo: categorías, unidades, proveedores, productos, ofertas e historial de costos."""

from app.modules.catalog.defaults import seed_catalog_defaults
from app.modules.catalog.router import router

__all__ = ["router", "seed_catalog_defaults"]
