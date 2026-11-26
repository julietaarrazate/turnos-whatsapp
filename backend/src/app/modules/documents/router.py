from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.db import DbSession
from app.core.permissions import Permission
from app.modules.auth import TenantContext, require
from app.modules.documents import service
from app.modules.documents.models import DocumentKind
from app.modules.documents.schemas import DocumentOut, DocumentUploadIn, StorageOut

router = APIRouter(prefix="/api/v1", tags=["documents"])

# Sube el archivo quien después lo va a adjuntar; lo descarga quien puede ver la entidad dueña
# (las rutas de descarga están en cada módulo: gastos y propuestas).
Expenses = Annotated[TenantContext, Depends(require(Permission.EXPENSES_EDIT))]
View = Annotated[TenantContext, Depends(require(Permission.ORG_VIEW))]
Decide = Annotated[TenantContext, Depends(require(Permission.PROPOSAL_DECIDE))]


@router.post("/documents/receipts", status_code=status.HTTP_201_CREATED)
def upload_receipt(body: DocumentUploadIn, ctx: Expenses, db: DbSession) -> DocumentOut:
    """La foto o el PDF del comprobante de un gasto. Se adjunta al crear o editar el gasto."""
    return service.upload(db, ctx, DocumentKind.RECEIPT, body)


@router.post("/documents/purchase-orders", status_code=status.HTTP_201_CREATED)
def upload_purchase_order(body: DocumentUploadIn, ctx: Decide, db: DbSession) -> DocumentOut:
    """La OC del cliente (PDF o foto). Se adjunta en la aprobación manual."""
    return service.upload(db, ctx, DocumentKind.PURCHASE_ORDER, body)


@router.get("/documents/storage")
def get_storage_usage(ctx: View, db: DbSession) -> StorageOut:
    """Cuánto ocupan los archivos de la organización y el tope (para avisar antes de llenarse)."""
    return StorageOut(
        used=service.storage_used(db, ctx.organization_id),
        limit=service.storage_quota(),
        enabled=service.uploads_enabled(),
    )
