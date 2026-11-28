import contextlib
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.core.config import get_settings, is_platform_admin
from app.core.db import AppSession, DbSession
from app.core.errors import AppError, ensure
from app.core.rate_limit import enforce
from app.core.storage import get_storage
from app.modules.auth import account, passkeys, service
from app.modules.auth.dependencies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    SESSION_HINT_COOKIE,
    Client,
    CurrentAuth,
    Public,
    access_token_from,
)
from app.modules.auth.schemas import (
    InvitationAccept,
    InvitationPreview,
    LoginRequest,
    MembershipOut,
    MeResponse,
    PasskeyCredential,
    PasskeyOut,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    PinCheckOut,
    PinIn,
    ProfileUpdate,
    SwitchOrganizationRequest,
    UserOut,
)
from app.modules.identity import User
from app.modules.notifications import send_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_PATH = "/api/v1/auth"


def _set_cookies(response: Response, tokens: service.IssuedTokens) -> None:
    settings = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_PATH,
    )
    # Indicador sin valor secreto, visible en todas las rutas: el frontend lo usa solo para
    # decidir si mandar a /login (el refresh token no viaja fuera de /api/v1/auth).
    response.set_cookie(
        SESSION_HINT_COOKIE,
        "1",
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    response.delete_cookie(SESSION_HINT_COOKIE, path="/")


def _me(db: AppSession, auth: service.AuthContext) -> MeResponse:
    user = ensure(db.get(User, auth.user_id), "usuario")
    memberships = service.active_memberships(db, auth.user_id)
    return MeResponse(
        user=UserOut(id=user.id, email=user.email, name=user.name),
        active_organization_id=auth.organization_id,
        role=auth.role,
        permissions=sorted(p.value for p in auth.permissions),
        memberships=[
            MembershipOut(organization_id=o.id, organization_name=o.name, role=m.role)
            for m, o in memberships
        ],
        uploads_enabled=get_storage() is not None,
        pin_enabled=user.pin_hash is not None,
        platform_admin=is_platform_admin(user.email),
    )


def _me_for_tokens(db: AppSession, tokens: service.IssuedTokens) -> MeResponse:
    return _me(db, service.resolve_access_token(db, tokens.access_token))


@router.post("/login", dependencies=[Public])
def login(body: LoginRequest, response: Response, db: DbSession, client: Client) -> MeResponse:
    enforce(f"login:ip:{client.ip}", limit=20, window_seconds=60)
    enforce(f"login:email:{body.email.lower()}", limit=10, window_seconds=900)
    tokens = service.login(db, body.email, body.password, client)
    _set_cookies(response, tokens)
    return _me_for_tokens(db, tokens)


@router.post("/refresh", dependencies=[Public])
def refresh(request: Request, response: Response, db: DbSession, client: Client) -> MeResponse:
    enforce(f"refresh:ip:{client.ip}", limit=60, window_seconds=60)
    tokens = service.refresh(db, request.cookies.get(REFRESH_COOKIE), client)
    _set_cookies(response, tokens)
    return _me_for_tokens(db, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Public])
def logout(request: Request, response: Response, db: DbSession) -> None:
    claims_session = None
    # Logout es idempotente: sin una sesión válida, solo limpia las cookies.
    with contextlib.suppress(AppError):
        claims_session = service.resolve_access_token(db, access_token_from(request)).session_id
    service.logout(db, request.cookies.get(REFRESH_COOKIE), claims_session)
    _clear_cookies(response)


@router.get("/me")
def me(auth: CurrentAuth, db: DbSession) -> MeResponse:
    return _me(db, auth)


@router.post("/switch-organization")
def switch_organization(
    body: SwitchOrganizationRequest,
    auth: CurrentAuth,
    response: Response,
    db: DbSession,
    client: Client,
) -> MeResponse:
    tokens = service.switch_organization(db, auth, body.organization_id, client)
    _set_cookies(response, tokens)
    return _me_for_tokens(db, tokens)


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED, dependencies=[Public])
def password_reset_request(
    body: PasswordResetRequest, db: DbSession, client: Client, background: BackgroundTasks
) -> None:
    enforce(f"reset:ip:{client.ip}", limit=10, window_seconds=900)
    enforce(f"reset:email:{body.email.lower()}", limit=3, window_seconds=900)
    message = service.request_password_reset(db, body.email)
    if message is not None:
        background.add_task(send_email, message)


@router.post(
    "/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Public]
)
def password_reset_confirm(
    body: PasswordResetConfirm, response: Response, db: DbSession, client: Client
) -> None:
    enforce(f"reset-confirm:ip:{client.ip}", limit=10, window_seconds=900)
    service.confirm_password_reset(db, body.token, body.password)
    _clear_cookies(response)


@router.get("/invitations/{token}", dependencies=[Public])
def invitation_preview(token: str, db: DbSession, client: Client) -> InvitationPreview:
    enforce(f"invite:ip:{client.ip}", limit=30, window_seconds=900)
    invitation, org_name, user_exists = service.preview_invitation(db, token)
    return InvitationPreview(
        organization_name=org_name,
        email=invitation.email,
        role=invitation.role,
        user_exists=user_exists,
    )


@router.post("/invitations/accept", dependencies=[Public])
def invitation_accept(
    body: InvitationAccept, response: Response, db: DbSession, client: Client
) -> MeResponse:
    enforce(f"invite:ip:{client.ip}", limit=30, window_seconds=900)
    tokens = service.accept_invitation(db, body.token, body.password, body.name, client)
    _set_cookies(response, tokens)
    return _me_for_tokens(db, tokens)


# --- Llaves de acceso: entrar con huella, cara o el bloqueo del teléfono ---------------


@router.post("/passkeys/login/options", dependencies=[Public])
def passkey_login_options(db: DbSession, client: Client) -> dict[str, Any]:
    enforce(f"passkey:ip:{client.ip}", limit=30, window_seconds=60)
    return passkeys.login_options(db)


@router.post("/passkeys/login", dependencies=[Public])
def passkey_login(
    body: PasskeyCredential, response: Response, db: DbSession, client: Client
) -> MeResponse:
    enforce(f"passkey:ip:{client.ip}", limit=30, window_seconds=60)
    tokens = passkeys.login(db, body.credential, client)
    _set_cookies(response, tokens)
    return _me_for_tokens(db, tokens)


@router.get("/passkeys")
def passkey_list(auth: CurrentAuth, db: DbSession) -> list[PasskeyOut]:
    return [
        PasskeyOut.model_validate(p, from_attributes=True) for p in passkeys.list_passkeys(db, auth)
    ]


@router.post("/passkeys/register/options")
def passkey_register_options(auth: CurrentAuth, db: DbSession) -> dict[str, Any]:
    return passkeys.registration_options(db, auth)


@router.post("/passkeys", status_code=status.HTTP_201_CREATED)
def passkey_register(
    body: PasskeyCredential, auth: CurrentAuth, db: DbSession, client: Client
) -> PasskeyOut:
    passkey = passkeys.register(db, auth, body.credential, client)
    return PasskeyOut.model_validate(passkey, from_attributes=True)


@router.delete("/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
def passkey_delete(passkey_id: UUID, auth: CurrentAuth, db: DbSession) -> None:
    passkeys.delete_passkey(db, auth, passkey_id)


# --- Mi perfil: nombre, contraseña y bloqueo con PIN -----------------------------------


@router.patch("/me")
def update_profile(body: ProfileUpdate, auth: CurrentAuth, db: DbSession) -> MeResponse:
    account.rename(db, auth.user_id, body.name)
    return _me(db, auth)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, auth: CurrentAuth, db: DbSession, client: Client) -> None:
    """Cambia la contraseña; las demás sesiones (otros teléfonos) se cierran."""
    enforce(f"password-change:user:{auth.user_id}", limit=10, window_seconds=900)
    account.change_password(
        db, auth.user_id, auth.session_id, body.current_password, body.new_password
    )


@router.put("/pin", status_code=status.HTTP_204_NO_CONTENT)
def set_pin(body: PinIn, auth: CurrentAuth, db: DbSession) -> None:
    """Activa o cambia el PIN del bloqueo de pantalla."""
    account.set_pin(db, auth.user_id, body.pin)


@router.delete("/pin", status_code=status.HTTP_204_NO_CONTENT)
def remove_pin(auth: CurrentAuth, db: DbSession) -> None:
    account.remove_pin(db, auth.user_id)


@router.post("/pin/check")
def check_pin(body: PinIn, auth: CurrentAuth, db: DbSession, response: Response) -> PinCheckOut:
    """Destraba la pantalla. A los 5 intentos mal seguidos se cierra la sesión."""
    enforce(f"pin:user:{auth.user_id}", limit=20, window_seconds=900)
    left = account.check_pin(db, auth.user_id, auth.session_id, body.pin)
    ok = left == account.MAX_PIN_FAILURES
    if left == 0:
        _clear_cookies(response)
    return PinCheckOut(ok=ok, attempts_left=left)
