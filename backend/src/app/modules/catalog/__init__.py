"""Catálogo: categorías, unidades, proveedores, productos, ofertas e historial de costos."""

from app.modules.catalog.costs import DEFAULT_STALENESS_DAYS, STALENESS_SETTING, today_ar
from app.modules.catalog.defaults import seed_catalog_defaults
from app.modules.catalog.models import Category, Product
from app.modules.catalog.router import router
from app.modules.catalog.service import LineSource, category_info, current_prices, line_source

__all__ = [
    "DEFAULT_STALENESS_DAYS",
    "STALENESS_SETTING",
    "Category",
    "LineSource",
    "Product",
    "category_info",
    "current_prices",
    "line_source",
    "router",
    "seed_catalog_defaults",
    "today_ar",
]
