from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.catalog import bulk, importer, service
from app.modules.catalog.schemas import (
    BulkIncreaseIn,
    BulkPreviewOut,
    CatalogImportIn,
    CatalogImportOut,
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    OfferIn,
    OfferOut,
    OfferUpdate,
    PriceIn,
    PriceOut,
    ProductIn,
    ProductOut,
    ProductPage,
    ProductUpdate,
    SupplierIn,
    SupplierOut,
    SupplierSummary,
    SupplierUpdate,
    UnitOut,
)

router = APIRouter(prefix="/api/v1", tags=["catalog"])

View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Edit = Annotated[TenantContext, Depends(require(Permission.CATALOG_EDIT))]
CostView = Annotated[TenantContext, Depends(require(Permission.COST_VIEW))]
CostEdit = Annotated[TenantContext, Depends(require(Permission.COSTS_EDIT))]


# --- Categorías y unidades -----------------------------------------------------------


@router.get("/categories")
def list_categories(ctx: View, db: DbSession) -> list[CategoryOut]:
    return service.list_categories(db, ctx)


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, ctx: Edit, db: DbSession) -> CategoryOut:
    return service.create_category(db, ctx, body)


@router.patch("/categories/{category_id}")
def update_category(
    category_id: UUID, body: CategoryUpdate, ctx: Edit, db: DbSession
) -> CategoryOut:
    return service.update_category(db, ctx, category_id, body)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: UUID, ctx: Edit, db: DbSession) -> None:
    service.delete_category(db, ctx, category_id)


@router.get("/units")
def list_units(ctx: View, db: DbSession) -> list[UnitOut]:
    return service.list_units(db, ctx)


# --- Proveedores -------------------------------------------------------------------------


@router.get("/suppliers")
def list_suppliers(
    ctx: View, db: DbSession, q: Annotated[str | None, Query(max_length=100)] = None
) -> list[SupplierSummary]:
    return service.list_suppliers(db, ctx, q)


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
def create_supplier(body: SupplierIn, ctx: Edit, db: DbSession) -> SupplierOut:
    return service.create_supplier(db, ctx, body)


@router.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: UUID, ctx: View, db: DbSession) -> SupplierOut:
    return service.get_supplier(db, ctx, supplier_id)


@router.patch("/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: UUID, body: SupplierUpdate, ctx: Edit, db: DbSession
) -> SupplierOut:
    return service.update_supplier(db, ctx, supplier_id, body)


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(supplier_id: UUID, ctx: Edit, db: DbSession) -> None:
    service.delete_supplier(db, ctx, supplier_id)


# --- Productos y ofertas -------------------------------------------------------------------


@router.get("/products")
def list_products(
    ctx: View,
    db: DbSession,
    *,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category_id: UUID | None = None,
    include_inactive: bool = False,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ProductPage:
    return service.list_products(
        db,
        ctx,
        q=q,
        category_id=category_id,
        include_inactive=include_inactive,
        cursor=cursor,
        limit=limit,
    )


@router.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(body: ProductIn, ctx: Edit, db: DbSession) -> ProductOut:
    return service.create_product(db, ctx, body)


@router.get("/products/{product_id}")
def get_product(product_id: UUID, ctx: View, db: DbSession) -> ProductOut:
    return service.get_product(db, ctx, product_id)


@router.patch("/products/{product_id}")
def update_product(product_id: UUID, body: ProductUpdate, ctx: Edit, db: DbSession) -> ProductOut:
    return service.update_product(db, ctx, product_id, body)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: UUID, ctx: Edit, db: DbSession) -> None:
    service.delete_product(db, ctx, product_id)


@router.post("/products/{product_id}/offers", status_code=status.HTTP_201_CREATED)
def create_offer(product_id: UUID, body: OfferIn, ctx: Edit, db: DbSession) -> ProductOut:
    """Agrega un proveedor que ofrece el producto. Cargar el costo inicial pide `costs.edit`."""
    return service.create_offer(db, ctx, product_id, body)


@router.patch("/offers/{offer_id}")
def update_offer(offer_id: UUID, body: OfferUpdate, ctx: Edit, db: DbSession) -> OfferOut:
    return service.update_offer(db, ctx, offer_id, body)


@router.get("/offers/{offer_id}/prices")
def list_prices(offer_id: UUID, ctx: CostView, db: DbSession) -> list[PriceOut]:
    """Historial de costos de la oferta, del más reciente al más viejo."""
    return service.list_prices(db, ctx, offer_id)


@router.post("/offers/{offer_id}/prices", status_code=status.HTTP_201_CREATED)
def record_price(offer_id: UUID, body: PriceIn, ctx: CostEdit, db: DbSession) -> OfferOut:
    """Registra un costo nuevo. El historial no se edita: un error se corrige con otro registro."""
    return service.record_price(db, ctx, offer_id, body)


# --- Aumento masivo e importación (C-09, C-10) ----------------------------------------------


@router.post("/catalog/bulk-increase/preview")
def preview_bulk_increase(body: BulkIncreaseIn, ctx: CostEdit, db: DbSession) -> BulkPreviewOut:
    """Simula el aumento: qué ofertas cambian y a cuánto, sin guardar nada."""
    return bulk.preview_bulk(db, ctx, body)


@router.post("/catalog/bulk-increase")
def bulk_increase(body: BulkIncreaseIn, ctx: CostEdit, db: DbSession) -> BulkPreviewOut:
    """Aplica el aumento: un costo nuevo por oferta (origen BULK_UPDATE)."""
    return bulk.apply_bulk(db, ctx, body)


@router.post("/catalog/import/preview")
def preview_catalog_import(body: CatalogImportIn, ctx: Edit, db: DbSession) -> CatalogImportOut:
    """Lee la planilla, sugiere el mapeo y muestra qué se importaría (con errores por fila)."""
    return importer.preview_import(db, ctx, body)


@router.post("/catalog/import")
def catalog_import(body: CatalogImportIn, ctx: Edit, db: DbSession) -> CatalogImportOut:
    """Importa las filas sin errores: categorías, proveedores, productos, ofertas y costos."""
    return importer.apply_import(db, ctx, body)
