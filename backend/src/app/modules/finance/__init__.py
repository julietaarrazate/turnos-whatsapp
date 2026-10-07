"""Finanzas: gastos reales del evento y presupuestado vs real (DOMAIN_MODEL §2.8)."""

from app.modules.finance.models import Expense
from app.modules.finance.router import router

__all__ = ["Expense", "router"]
