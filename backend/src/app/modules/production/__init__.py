"""Producción: lista de contratación por proveedor y tareas (PRODUCT_SPEC §4.9)."""

from app.modules.production.router import router
from app.modules.production.service import Pending, PendingKind, pending_operations

__all__ = ["Pending", "PendingKind", "pending_operations", "router"]
