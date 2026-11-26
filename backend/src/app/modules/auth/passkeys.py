"""Entrar con huella, cara o el bloqueo del teléfono (llaves de acceso / WebAuthn).

El dispositivo guarda la clave privada y pide la huella o el PIN del teléfono; el servidor solo
guarda la clave pública y verifica la firma. Es el estándar de Apple, Google y Microsoft, y es
gratis: no hay servicio externo de por medio.
"""

import json
import secrets
from base64 import urlsafe_b64decode
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import delete, select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import get_settings
from app.core.db import AppSession
from app.core.errors import AppError, ensure
from app.core.security import token_hash, utcnow
from app.modules.auth.models import Passkey, WebauthnChallenge
from app.modules.auth.service import AuthContext, ClientInfo, IssuedTokens, login_user
from app.modules.identity import User

CHALLENGE_TTL = timedelta(minutes=5)
MAX_PASSKEYS = 10


def _rp() -> tuple[str, str]:
    """(rp_id, origen esperado). El navegador firma el origen: tiene que ser el del frontend."""
    settings = get_settings()
    parts = urlsplit(settings.app_base_url)
    origin = f"{parts.scheme}://{parts.netloc}"
    return settings.webauthn_rp_id or ensure(parts.hostname, "dominio"), origin


def _b64url(data: str) -> bytes:
    return urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _new_challenge(db: AppSession, purpose: str, user_id: UUID | None) -> bytes:
    now = utcnow()
    # Limpieza barata: los desafíos viejos no sirven para nada.
    db.execute(delete(WebauthnChallenge).where(WebauthnChallenge.expires_at < now - CHALLENGE_TTL))
    challenge = secrets.token_bytes(32)
    db.add(
        WebauthnChallenge(
            challenge_hash=token_hash(bytes_to_base64url(challenge)),
            user_id=user_id,
            purpose=purpose,
            expires_at=now + CHALLENGE_TTL,
        )
    )
    db.flush()
    return challenge


def _invalid(detail: str = "No se pudo verificar la llave. Probá de nuevo.") -> AppError:
    return AppError(400, "passkey_invalid", detail)


def _consume_challenge(
    db: AppSession, credential: dict[str, Any], purpose: str, user_id: UUID | None
) -> bytes:
    """Lee el desafío firmado por el navegador y lo marca usado (un solo uso, 5 minutos)."""
    try:
        client_data = json.loads(_b64url(credential["response"]["clientDataJSON"]))
        challenge = str(client_data["challenge"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid() from exc
    row = db.execute(
        select(WebauthnChallenge)
        .where(WebauthnChallenge.challenge_hash == token_hash(challenge))
        .with_for_update()
    ).scalar_one_or_none()
    if (
        row is None
        or row.purpose != purpose
        or row.used_at is not None
        or row.expires_at <= utcnow()
        or row.user_id != user_id
    ):
        raise _invalid("Se venció el pedido. Probá de nuevo.")
    row.used_at = utcnow()
    return _b64url(challenge)


def _device_name(client: ClientInfo) -> str:
    agent = (client.user_agent or "").lower()
    for needle, name in (
        ("iphone", "iPhone"),
        ("ipad", "iPad"),
        ("android", "Android"),
        ("macintosh", "Mac"),
        ("windows", "Windows"),
    ):
        if needle in agent:
            return name
    return "Dispositivo"


# --- Registrar una llave (con la sesión abierta) ----------------------------------------


def registration_options(db: AppSession, auth: AuthContext) -> dict[str, Any]:
    user = ensure(db.get(User, auth.user_id), "usuario")
    existing = db.execute(select(Passkey.credential_id).where(Passkey.user_id == user.id))
    rp_id, _ = _rp()
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=get_settings().app_name,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.name,
        challenge=_new_challenge(db, "REGISTER", user.id),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c) for c in existing.scalars()],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    result: dict[str, Any] = json.loads(options_to_json(options))
    return result


def register(
    db: AppSession, auth: AuthContext, credential: dict[str, Any], client: ClientInfo
) -> Passkey:
    count = len(db.execute(select(Passkey.id).where(Passkey.user_id == auth.user_id)).all())
    if count >= MAX_PASSKEYS:
        raise AppError(409, "too_many_passkeys", "Ya tenés 10 dispositivos: borrá alguno")
    challenge = _consume_challenge(db, credential, "REGISTER", auth.user_id)
    rp_id, origin = _rp()
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        raise _invalid() from exc
    passkey = Passkey(
        user_id=auth.user_id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=_device_name(client),
    )
    db.add(passkey)
    db.flush()
    return passkey


def list_passkeys(db: AppSession, auth: AuthContext) -> list[Passkey]:
    return list(
        db.execute(
            select(Passkey).where(Passkey.user_id == auth.user_id).order_by(Passkey.created_at)
        ).scalars()
    )


def delete_passkey(db: AppSession, auth: AuthContext, passkey_id: UUID) -> None:
    passkey = db.get(Passkey, passkey_id)
    if passkey is None or passkey.user_id != auth.user_id:
        raise AppError(404, "not_found", "No encontramos ese dispositivo")
    db.delete(passkey)


# --- Entrar con la llave (sin sesión) ---------------------------------------------------


def login_options(db: AppSession) -> dict[str, Any]:
    rp_id, _ = _rp()
    options = generate_authentication_options(
        rp_id=rp_id,
        challenge=_new_challenge(db, "LOGIN", None),
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    result: dict[str, Any] = json.loads(options_to_json(options))
    return result


def login(db: AppSession, credential: dict[str, Any], client: ClientInfo) -> IssuedTokens:
    challenge = _consume_challenge(db, credential, "LOGIN", None)
    try:
        raw_id = _b64url(str(credential["rawId"]))
    except (KeyError, ValueError) as exc:
        raise _invalid() from exc
    passkey = db.execute(
        select(Passkey).where(Passkey.credential_id == raw_id).with_for_update()
    ).scalar_one_or_none()
    if passkey is None:
        raise _invalid("Este dispositivo ya no está habilitado: entrá con mail y contraseña.")
    handle = (credential.get("response") or {}).get("userHandle")
    if handle and _b64url(str(handle)) != passkey.user_id.bytes:
        raise _invalid()
    rp_id, origin = _rp()
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        raise _invalid() from exc
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = utcnow()
    user = db.get(User, passkey.user_id)
    if user is None or not user.is_active:
        raise AppError(401, "invalid_credentials", "La cuenta no está activa")
    return login_user(db, user, client)
