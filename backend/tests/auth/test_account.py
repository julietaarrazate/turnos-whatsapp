"""Mi perfil: nombre, cambiar contraseña y bloqueo de pantalla con PIN."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.auth.test_login import login
from tests.factories import DEFAULT_PASSWORD, create_member


def _client() -> TestClient:
    return TestClient(create_app(), headers={"X-Requested-With": "fetch"})


def test_rename_and_change_password_closes_the_other_sessions(client: TestClient) -> None:
    member = create_member("owner@example.com")
    login(client, member.email)
    other_phone = _client()
    login(other_phone, member.email)

    renamed = client.patch("/api/v1/auth/me", json={"name": "  Julieta   Arrazate "})
    assert renamed.json()["user"]["name"] == "Julieta Arrazate"

    wrong = client.post(
        "/api/v1/auth/password",
        json={"current_password": "otra-cosa-123", "new_password": "nueva-clave-segura"},
    )
    assert (wrong.status_code, wrong.json()["code"]) == (422, "wrong_password")
    ok = client.post(
        "/api/v1/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "nueva-clave-segura"},
    )
    assert ok.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 200  # esta sesión sigue
    assert other_phone.get("/api/v1/auth/me").status_code == 401  # el otro teléfono no
    login(_client(), member.email, "nueva-clave-segura")


def test_pin_lock_unlocks_and_five_mistakes_close_the_session(client: TestClient) -> None:
    member = create_member("owner@example.com")
    login(client, member.email)
    assert client.get("/api/v1/auth/me").json()["pin_enabled"] is False
    assert client.post("/api/v1/auth/pin/check", json={"pin": "2580"}).status_code == 409

    easy = client.put("/api/v1/auth/pin", json={"pin": "1111"})
    assert (easy.status_code, easy.json()["code"]) == (422, "pin_too_easy")
    letters = client.put("/api/v1/auth/pin", json={"pin": "12a4"})
    assert (letters.status_code, letters.json()["code"]) == (422, "pin_invalid")
    assert client.put("/api/v1/auth/pin", json={"pin": "2580"}).status_code == 204
    assert client.get("/api/v1/auth/me").json()["pin_enabled"] is True

    bad = client.post("/api/v1/auth/pin/check", json={"pin": "0000"}).json()
    assert bad == {"ok": False, "attempts_left": 4}
    good = client.post("/api/v1/auth/pin/check", json={"pin": "2580"}).json()
    assert good == {"ok": True, "attempts_left": 5}  # acertar reinicia la cuenta

    for left in (4, 3, 2, 1):
        assert (
            client.post("/api/v1/auth/pin/check", json={"pin": "0000"}).json()["attempts_left"]
            == left
        )
    last = client.post("/api/v1/auth/pin/check", json={"pin": "0000"})
    assert last.json() == {"ok": False, "attempts_left": 0}
    assert client.get("/api/v1/auth/me").status_code == 401  # hay que volver a entrar


def test_remove_pin(client: TestClient) -> None:
    member = create_member("owner@example.com")
    login(client, member.email)
    client.put("/api/v1/auth/pin", json={"pin": "2580"})
    assert client.delete("/api/v1/auth/pin").status_code == 204
    assert client.get("/api/v1/auth/me").json()["pin_enabled"] is False
