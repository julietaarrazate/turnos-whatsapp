from app.core.enums import Role
from tests.security.harness import build_org, logged_in


def test_create_read_update_and_delete_client() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    created = owner.post(
        "/api/v1/clients",
        json={
            "name": "  Banco Andino ",
            "tax_id": "30-71234567-1",
            "tax_condition": "RI",
            "contacts": [
                {"name": "Ana", "email": "ANA@banco.example.com", "is_primary": True},
                {"name": "Beto", "is_primary": True},
            ],
        },
    )
    assert created.status_code == 201, created.text
    client = created.json()
    assert client["name"] == "Banco Andino"
    # Un solo contacto principal: gana el primero.
    assert [(c["name"], c["is_primary"]) for c in client["contacts"]] == [
        ("Ana", True),
        ("Beto", False),
    ]
    assert client["contacts"][0]["email"] == "ana@banco.example.com"

    updated = owner.patch(
        f"/api/v1/clients/{client['id']}", json={"city": "Rosario", "contacts": [{"name": "Caro"}]}
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Rosario"
    assert [c["name"] for c in updated.json()["contacts"]] == ["Caro"]

    assert owner.delete(f"/api/v1/clients/{client['id']}").status_code == 204
    assert owner.get(f"/api/v1/clients/{client['id']}").status_code == 404
    actions = [e["action"] for e in owner.get("/api/v1/audit-logs").json()["items"]]
    assert {"client.created", "client.updated", "client.deleted"} <= set(actions)


def test_client_names_are_unique_ignoring_case_but_reusable_after_delete() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    first = owner.post("/api/v1/clients", json={"name": "Acme"}).json()
    duplicate = owner.post("/api/v1/clients", json={"name": "ACME"})
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "client_name_taken"
    owner.delete(f"/api/v1/clients/{first['id']}")
    assert owner.post("/api/v1/clients", json={"name": "Acme"}).status_code == 201


def test_list_searches_and_paginates_by_name() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    for name in ("Delta", "alfa", "Charlie", "Bravo"):
        owner.post("/api/v1/clients", json={"name": name})
    first = owner.get("/api/v1/clients", params={"limit": 3}).json()
    # "Cliente ejemplo" lo crea el harness.
    assert [c["name"] for c in first["items"]] == ["alfa", "Bravo", "Charlie"]
    second = owner.get(
        "/api/v1/clients", params={"limit": 3, "cursor": first["next_cursor"]}
    ).json()
    assert [c["name"] for c in second["items"]] == ["Cliente ejemplo", "Delta"]
    assert second["next_cursor"] is None
    found = owner.get("/api/v1/clients", params={"q": "ARL"}).json()["items"]
    assert [c["name"] for c in found] == ["Charlie"]


def test_invalid_cuit_is_rejected() -> None:
    owner = logged_in(build_org("a").members[Role.OWNER])
    response = owner.post("/api/v1/clients", json={"name": "X", "tax_id": "123"})
    assert response.status_code == 422
