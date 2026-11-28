from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.db import DbSession
from app.modules.auth import Client, CurrentAuth
from app.modules.push import service

router = APIRouter(prefix="/api/v1/push", tags=["push"])


class PushKeysIn(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=10, max_length=100)


class PushSubscriptionIn(BaseModel):
    """Lo que devuelve ``PushSubscription.toJSON()`` en el navegador."""

    endpoint: str = Field(max_length=1000)
    keys: PushKeysIn


class PushEndpointIn(BaseModel):
    endpoint: str = Field(max_length=1000)


class PushStatusOut(BaseModel):
    public_key: str  # applicationServerKey para pushManager.subscribe
    devices: int  # cuántos dispositivos de esta persona reciben avisos


class PushTestOut(BaseModel):
    sent: int


@router.get("")
def push_status(auth: CurrentAuth, db: DbSession) -> PushStatusOut:
    return PushStatusOut(
        public_key=service.keys(db).public_key, devices=service.has_devices(db, auth.user_id)
    )


@router.post("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(body: PushSubscriptionIn, auth: CurrentAuth, db: DbSession, client: Client) -> None:
    """Este dispositivo empieza a recibir avisos."""
    service.subscribe(
        db,
        auth.user_id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=client.user_agent,
    )


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(body: PushEndpointIn, auth: CurrentAuth, db: DbSession) -> None:
    service.unsubscribe(db, auth.user_id, body.endpoint)


@router.post("/test")
def test(auth: CurrentAuth, db: DbSession) -> PushTestOut:
    """Manda un aviso de prueba a los dispositivos de quien lo pide."""
    return PushTestOut(sent=service.send_test(db, auth.user_id))
