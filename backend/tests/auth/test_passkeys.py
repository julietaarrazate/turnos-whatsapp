"""Entrar con huella, cara o el bloqueo del teléfono (llaves de acceso / WebAuthn).

Un "teléfono simulado" firma con una clave EC P-256 igual que lo haría uno real.
"""

import hashlib
import json
import struct
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.core.enums import Role
from tests.auth.test_login import login
from tests.factories import create_member

ORIGIN = "http://localhost:3000"
RP_ID = "localhost"


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return urlsafe_b64decode(data + "=" * (-len(data) % 4))


class FakeDevice:
    """Autenticador de software: guarda la clave privada como lo hace el teléfono."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = b"cred-" + hashlib.sha256(str(id(self)).encode()).digest()[:16]
        self.user_handle: bytes | None = None
        self.count = 0

    def _cose_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, kind: str, challenge: str, origin: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": origin}).encode()

    def create(self, options: dict[str, Any], origin: str = ORIGIN) -> dict[str, Any]:
        self.user_handle = _unb64(options["user"]["id"])
        client_data = self._client_data("webauthn.create", options["challenge"], origin)
        auth_data = (
            hashlib.sha256(options["rp"]["id"].encode()).digest()
            + bytes([0x45])  # presencia + verificación (huella) + datos de la credencial
            + struct.pack(">I", 0)
            + bytes(16)
            + struct.pack(">H", len(self.credential_id))
            + self.credential_id
            + self._cose_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": _b64(self.credential_id),
            "rawId": _b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64(client_data),
                "attestationObject": _b64(attestation),
            },
        }

    def get(self, options: dict[str, Any], verified: bool = True) -> dict[str, Any]:
        self.count += 1
        client_data = self._client_data("webauthn.get", options["challenge"], ORIGIN)
        flags = 0x05 if verified else 0x01
        auth_data = (
            hashlib.sha256(options["rpId"].encode()).digest()
            + bytes([flags])
            + struct.pack(">I", self.count)
        )
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": _b64(self.credential_id),
            "rawId": _b64(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": _b64(client_data),
                "authenticatorData": _b64(auth_data),
                "signature": _b64(signature),
                "userHandle": _b64(self.user_handle or b""),
            },
        }


def _register(client: TestClient, device: FakeDevice) -> dict[str, Any]:
    options = client.post("/api/v1/auth/passkeys/register/options").json()
    assert options["rp"]["id"] == RP_ID
    assert options["authenticatorSelection"]["userVerification"] == "required"
    response = client.post(
        "/api/v1/auth/passkeys",
        json={"credential": device.create(options)},
        headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _passkey_login(client: TestClient, device: FakeDevice, **kwargs: Any) -> Any:
    options = client.post("/api/v1/auth/passkeys/login/options").json()
    return client.post(
        "/api/v1/auth/passkeys/login", json={"credential": device.get(options, **kwargs)}
    )


def test_register_on_a_device_and_then_enter_without_password(client: TestClient) -> None:
    member = create_member("owner@example.com", Role.OWNER)
    login(client, member.email)
    device = FakeDevice()
    created = _register(client, device)
    assert created["name"] == "iPhone"
    assert [p["id"] for p in client.get("/api/v1/auth/passkeys").json()] == [created["id"]]

    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401

    entered = _passkey_login(client, device)
    assert entered.status_code == 200, entered.text
    assert entered.json()["user"]["email"] == "owner@example.com"
    assert entered.json()["role"] == "OWNER"
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/auth/passkeys").json()[0]["last_used_at"] is not None


def test_challenge_is_single_use_and_signature_must_match(client: TestClient) -> None:
    member = create_member("owner@example.com")
    login(client, member.email)
    device = FakeDevice()
    _register(client, device)
    client.post("/api/v1/auth/logout")

    options = client.post("/api/v1/auth/passkeys/login/options").json()
    credential = device.get(options)
    assert (
        client.post("/api/v1/auth/passkeys/login", json={"credential": credential}).status_code
        == 200
    )
    # El mismo desafío no sirve dos veces (alguien que copió la respuesta no entra).
    replay = client.post("/api/v1/auth/passkeys/login", json={"credential": credential})
    assert (replay.status_code, replay.json()["code"]) == (400, "passkey_invalid")

    # Otra clave (otro teléfono que dice ser este) no entra.
    impostor = FakeDevice()
    impostor.credential_id = device.credential_id
    impostor.user_handle = device.user_handle
    assert _passkey_login(client, impostor).status_code == 400

    # Sin huella / PIN del teléfono (solo "presencia"), tampoco.
    assert _passkey_login(client, device, verified=False).status_code == 400


def test_a_device_never_registered_or_removed_cannot_enter(client: TestClient) -> None:
    member = create_member("owner@example.com")
    login(client, member.email)
    device = FakeDevice()
    created = _register(client, device)

    other = create_member("otro@example.com")
    other_client = TestClient(client.app, headers={"X-Requested-With": "fetch"})
    login(other_client, other.email)
    # Las llaves de otra persona no se ven ni se borran.
    assert other_client.get("/api/v1/auth/passkeys").json() == []
    assert other_client.delete(f"/api/v1/auth/passkeys/{created['id']}").status_code == 404

    assert client.delete(f"/api/v1/auth/passkeys/{created['id']}").status_code == 204
    client.post("/api/v1/auth/logout")
    gone = _passkey_login(client, device)
    assert (gone.status_code, gone.json()["code"]) == (400, "passkey_invalid")
    assert _passkey_login(client, FakeDevice()).status_code == 400


def test_register_needs_a_session_and_the_right_site(client: TestClient) -> None:
    assert client.post("/api/v1/auth/passkeys/register/options").status_code == 401
    member = create_member("owner@example.com")
    login(client, member.email)
    options = client.post("/api/v1/auth/passkeys/register/options").json()
    # Una página falsa (otro dominio) no puede registrar una llave para esta cuenta.
    phishing = FakeDevice().create(options, origin="https://productoras-falsa.com")
    response = client.post("/api/v1/auth/passkeys", json={"credential": phishing})
    assert (response.status_code, response.json()["code"]) == (400, "passkey_invalid")
    assert client.get("/api/v1/auth/passkeys").json() == []
