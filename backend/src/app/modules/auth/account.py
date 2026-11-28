"""Mi perfil: nombre, cambiar contraseña y el bloqueo de pantalla con PIN.

El bloqueo no cierra la sesión: tapa la app cuando se minimiza o queda quieta, y se destraba con
el PIN (o la huella). El PIN se controla acá, no en el teléfono: a los 5 intentos mal seguidos
se cierra la sesión y hay que volver a entrar con email y contraseña.
"""

import re
from uuid import UUID

from sqlalchemy import update

from app.core.db import AppSession
from app.core.errors import AppError, ensure
from app.core.security import hash_password, utcnow, verify_password
from app.modules.auth.models import AuthSession
from app.modules.identity import User

MAX_PIN_FAILURES = 5
_PIN = re.compile(r"^\d{4}$")


def _user(db: AppSession, user_id: UUID) -> User:
    return ensure(db.get(User, user_id), "usuario")


def rename(db: AppSession, user_id: UUID, name: str) -> None:
    clean = " ".join(name.split())
    if len(clean) < 2:
        raise AppError(422, "name_required", "Poné tu nombre")
    _user(db, user_id).name = clean


def change_password(
    db: AppSession, user_id: UUID, session_id: UUID, current: str, new: str
) -> None:
    """Cambia la contraseña y cierra las demás sesiones (esta sigue abierta)."""
    user = _user(db, user_id)
    if not verify_password(user.password_hash, current):
        raise AppError(422, "wrong_password", "La contraseña actual no es correcta")
    if current == new:
        raise AppError(422, "same_password", "La nueva tiene que ser distinta de la actual")
    user.password_hash = hash_password(new)
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.id != session_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow(), revoked_reason="password_changed")
    )


def set_pin(db: AppSession, user_id: UUID, pin: str) -> None:
    if not _PIN.fullmatch(pin):
        raise AppError(422, "pin_invalid", "El PIN son 4 números")
    if len(set(pin)) == 1 or pin in {"1234", "4321", "0123", "9876"}:
        raise AppError(422, "pin_too_easy", "Elegí un PIN menos fácil de adivinar")
    user = _user(db, user_id)
    user.pin_hash = hash_password(pin)
    user.pin_failures = 0


def remove_pin(db: AppSession, user_id: UUID) -> None:
    user = _user(db, user_id)
    user.pin_hash = None
    user.pin_failures = 0


def check_pin(db: AppSession, user_id: UUID, session_id: UUID, pin: str) -> int:
    """Destraba la pantalla. Devuelve los intentos que quedan; con 0, la sesión ya se cerró."""
    user = _user(db, user_id)
    if user.pin_hash is None:
        raise AppError(409, "pin_not_set", "No tenés un PIN configurado")
    if _PIN.fullmatch(pin) and verify_password(user.pin_hash, pin):
        user.pin_failures = 0
        return MAX_PIN_FAILURES
    user.pin_failures += 1
    left = MAX_PIN_FAILURES - user.pin_failures
    if left <= 0:
        user.pin_failures = 0
        db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow(), revoked_reason="pin_failures")
        )
    return max(left, 0)
