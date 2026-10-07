"""Catálogo: categorías, unidades, proveedores, productos, ofertas e historial de costos."""

from app.modules.catalog.costs import DEFAULT_STALENESS_DAYS, STALENESS_SETTING, today_ar
from app.modules.catalog.defaults import seed_catalog_defaults
from app.modules.catalog.models import Category, Product
from app.modules.catalog.packages import PackageLine, package_spec
from app.modules.catalog.router import router
from app.modules.catalog.service import (
    LineSource,
    category_info,
    current_prices,
    line_source,
    supplier_name,
)

__all__ = [
    "DEFAULT_STALENESS_DAYS",
    "STALENESS_SETTING",
    "Category",
    "LineSource",
    "PackageLine",
    "Product",
    "category_info",
    "current_prices",
    "line_source",
    "package_spec",
    "router",
    "seed_catalog_defaults",
    "supplier_name",
    "today_ar",
]
