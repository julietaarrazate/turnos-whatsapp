"""Primitivas de seguridad: contraseñas (argon2id), tokens opacos y JWT de acceso."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()
# Se verifica contra este hash cuando el usuario no existe, para no filtrar por tiempo de
# respuesta qué emails están registrados.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128
_JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    """Token opaco de 256 bits, apto para URLs."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """En la base solo se guarda el hash: un dump no expone tokens válidos."""
    return hashlib.sha256(token.encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    organization_id: UUID | None


def encode_access_token(claims: AccessClaims) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {
        "typ": "access",
        "sub": str(claims.user_id),
        "sid": str(claims.session_id),
        "org": str(claims.organization_id) if claims.organization_id else None,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessClaims | None:
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret.get_secret_value(),
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "sid", "typ"]},
        )
        if payload["typ"] != "access":
            return None
        org = payload.get("org")
        return AccessClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
            organization_id=UUID(org) if org else None,
        )
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
