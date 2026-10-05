"""`Idempotency-Key` (ARCHITECTURE §4.5): un reintento con la misma clave devuelve la misma
respuesta en lugar de repetir la operación. Pensado para redes inestables en campo."""

import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import ForeignKey, String, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AppSession, Base
from app.core.errors import AppError


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[UUID]
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


def _fingerprint(scope: str, payload: Any) -> str:
    raw = json.dumps([scope, payload], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def run_idempotent[T: BaseModel](
    db: AppSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    key: str | None,
    scope: str,
    payload: Any,
    model: type[T],
    run: Callable[[], T],
) -> T:
    """Sin clave, ejecuta. Con clave: la primera vez ejecuta y guarda la respuesta; las
    siguientes la devuelven. Dos requests simultáneos con la misma clave se serializan en el
    INSERT (el segundo espera el COMMIT del primero)."""
    if key is None:
        return run()
    fingerprint = _fingerprint(scope, payload)
    inserted = db.execute(
        insert(IdempotencyKey)
        .values(organization_id=organization_id, key=key, user_id=user_id, request_hash=fingerprint)
        .on_conflict_do_nothing()
        .returning(IdempotencyKey.key)
    ).scalar_one_or_none()
    if inserted is None:
        row = db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.organization_id == organization_id, IdempotencyKey.key == key
            )
        ).scalar_one()
        if row.user_id != user_id or row.request_hash != fingerprint:
            raise AppError(
                422, "idempotency_key_reused", "Esa Idempotency-Key ya se usó para otra operación"
            )
        if row.response is None:  # pragma: no cover - solo si el primero falló sin rollback
            raise AppError(
                409, "idempotency_in_progress", "La operación todavía se está procesando"
            )
        return model.model_validate(row.response)
    result = run()
    row = db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.organization_id == organization_id, IdempotencyKey.key == key
        )
    ).scalar_one()
    row.response = result.model_dump(mode="json")
    db.flush()
    return result
