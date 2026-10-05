"""Permisos y su mapeo desde los roles fijos (PRODUCT_SPEC §9).

Este módulo es la única fuente de verdad de la matriz. Los endpoints declaran el permiso que
necesitan; nunca preguntan por el rol directamente.
"""

from collections.abc import Mapping
from enum import StrEnum

from app.core.enums import Role


class Permission(StrEnum):
    ORG_VIEW = "org.view"
    ORG_SETTINGS_MANAGE = "org.settings.manage"  # marca, valores por defecto
    ORG_FISCAL_MANAGE = "org.fiscal.manage"  # datos fiscales, baja de la organización
    MEMBERS_VIEW = "members.view"
    MEMBERS_MANAGE = "members.manage"  # invitar, cambiar rol, desactivar
    AUDIT_VIEW = "audit.view"
    DASHBOARD_VIEW = "dashboard.view"
    COST_VIEW = "cost.view"  # costos de proveedor
    MARGIN_VIEW = "margin.view"  # markup, margen, ganancia
    CLIENTS_EDIT = "clients.edit"
    CATALOG_EDIT = "catalog.edit"  # proveedores, productos, paquetes
    COSTS_EDIT = "costs.edit"  # cargar costos, aumento masivo, importar
    PRICING_SETTINGS = "pricing.settings"  # markups por categoría, margen mínimo
    BUDGET_EDIT = "budget.edit"
    MARKUP_OVERRIDE = "budget.markup_override"
    PROPOSAL_SEND = "proposal.send"
    PROPOSAL_DECIDE = "proposal.decide"  # aprobación manual con OC, marcar perdido
    PRODUCTION_MANAGE = "production.manage"
    EXPENSES_EDIT = "expenses.edit"
    EVENT_CLOSE = "event.close"


P = Permission

_COMMERCIAL = {
    P.ORG_VIEW,
    P.MEMBERS_VIEW,
    P.DASHBOARD_VIEW,
    P.COST_VIEW,
    P.MARGIN_VIEW,
    P.CLIENTS_EDIT,
    P.BUDGET_EDIT,
    P.MARKUP_OVERRIDE,
    P.PROPOSAL_SEND,
}

_MANAGER = _COMMERCIAL | {
    P.CATALOG_EDIT,
    P.COSTS_EDIT,
    P.PROPOSAL_DECIDE,
    P.PRODUCTION_MANAGE,
    P.EXPENSES_EDIT,
    P.EVENT_CLOSE,
}

_ADMIN = _MANAGER | {
    P.ORG_SETTINGS_MANAGE,
    P.MEMBERS_MANAGE,
    P.AUDIT_VIEW,
    P.PRICING_SETTINGS,
}

ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(_ADMIN | {P.ORG_FISCAL_MANAGE}),
    Role.ADMIN: frozenset(_ADMIN),
    Role.MANAGER: frozenset(_MANAGER),
    Role.QUOTER: frozenset(_COMMERCIAL),
    # Producción ve costos (paga proveedores) pero nunca márgenes.
    Role.PRODUCTION: frozenset(
        {P.ORG_VIEW, P.MEMBERS_VIEW, P.COST_VIEW, P.PRODUCTION_MANAGE, P.EXPENSES_EDIT}
    ),
    Role.VIEWER: frozenset({P.ORG_VIEW, P.MEMBERS_VIEW, P.DASHBOARD_VIEW}),
}

# Configuración de la organización: si VIEWER puede ver costos y márgenes.
VIEWER_SEES_FINANCIALS = "viewer_sees_financials"


def permissions_for(role: Role, org_settings: Mapping[str, object]) -> frozenset[Permission]:
    granted = ROLE_PERMISSIONS[role]
    if role is Role.VIEWER and org_settings.get(VIEWER_SEES_FINANCIALS) is True:
        granted = granted | {P.COST_VIEW, P.MARGIN_VIEW}
    return granted
