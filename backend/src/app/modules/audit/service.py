"""Registro de auditoría. Se escribe en la MISMA transacción que el cambio auditado."""

from enum import StrEnum
from typing import Any
from uuid import UUID

from app.core.db import AppSession
from app.core.request_context import request_id_var
from app.modules.audit.models import AuditLog


class ActorType(StrEnum):
    USER = "USER"
    PUBLIC_TOKEN = "PUBLIC_TOKEN"  # noqa: S105 — tipo de actor, no una contraseña
    SYSTEM = "SYSTEM"
    AI = "AI"


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Solo los campos que cambiaron."""
    changed = {k for k in after if before.get(k) != after.get(k)}
    return {k: before.get(k) for k in changed}, {k: after[k] for k in changed}


def record(
    db: AppSession,
    *,
    organization_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    actor_user_id: UUID | None,
    actor_type: ActorType = ActorType.USER,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_type=actor_type.value,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            ip=ip,
            user_agent=(user_agent or "")[:400] or None,
            request_id=request_id_var.get(),
        )
    )
