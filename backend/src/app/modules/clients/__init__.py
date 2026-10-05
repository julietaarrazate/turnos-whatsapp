"""Clientes (CRM liviano): empresas, contactos e historial comercial."""

from app.modules.clients.models import Client
from app.modules.clients.router import router

__all__ = ["Client", "router"]
