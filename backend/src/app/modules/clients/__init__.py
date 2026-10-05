"""Clientes (CRM liviano): empresas, contactos e historial comercial."""

from app.modules.clients.models import Client
from app.modules.clients.router import router
from app.modules.clients.service import get_active, get_or_create_by_name

__all__ = ["Client", "get_active", "get_or_create_by_name", "router"]
