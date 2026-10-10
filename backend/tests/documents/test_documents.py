"""Archivos subidos: comprobantes de gastos y OC de aprobaciones manuales (D-17, O-04, P-06)."""

from base64 import b64encode
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.core.config import Settings
from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.core.errors import AppError
from app.core.storage import LocalStorage, S3Storage, get_storage
from app.modules.documents.service import MAX_BYTES, clean_filename, sniff
from tests.production.test_production import _approved
from tests.proposals.test_proposals import _ok, _send
from tests.security.harness import OrgWorld, build_org, logged_in

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60
PDF = b"%PDF-1.7\n" + b"0" * 60


def _upload(
    client: TestClient, data: bytes, name: str = "ticket.jpg", kind: str = "receipts"
) -> Any:
    body = {"filename": name, "file_base64": b64encode(data).decode()}
    return client.post(f"/api/v1/documents/{kind}", json=body)


def _expenses_url(world: OrgWorld) -> str:
    return f"/api/v1/events/{world.ids['event_id']}/expenses"


def _expense(client: TestClient, world: OrgWorld, **body: Any) -> Any:
    category = str(world.ids["category_id"])
    return client.post(
        _expenses_url(world),
        json={"description": "Flete", "amount": "100", "category_id": category, **body},
    )


def test_sniff_detects_the_real_type_by_content() -> None:
    assert sniff(JPEG) == "image/jpeg"
    assert sniff(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8) == "image/png"
    assert sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff(b"\x00\x00\x00\x18ftypheic\x00\x00") == "image/heic"
    assert sniff(PDF) == "application/pdf"
    assert sniff(b"<html><script>alert(1)</script>") is None
    assert sniff(b"") is None


def test_clean_filename_keeps_only_a_safe_name() -> None:
    assert clean_filename("C:\\fotos\\ticket.jpg") == "ticket.jpg"
    assert clean_filename("../../etc/passwd") == "passwd"
    assert clean_filename('fac"tura\n.pdf') == "factura.pdf"
    assert clean_filename("   ") == "archivo"
    assert len(clean_filename("a" * 500)) == 200


def test_receipt_upload_validates_type_size_and_encoding() -> None:
    world = build_org("a")
    production = logged_in(world.members[Role.PRODUCTION])
    uploaded = _ok(_upload(production, JPEG, "Ticket café.jpg"), 201)
    assert uploaded["kind"] == "RECEIPT"
    assert (uploaded["mime"], uploaded["size"], uploaded["filename"]) == (
        "image/jpeg",
        len(JPEG),
        "Ticket café.jpg",
    )
    # La extensión no importa: manda el contenido.
    html = _upload(production, b"<html><script>alert(1)</script></html>", "foto.jpg")
    assert (html.status_code, html.json()["code"]) == (415, "upload_unsupported")
    too_big = _upload(production, JPEG + b"\x00" * MAX_BYTES)
    assert (too_big.status_code, too_big.json()["code"]) == (413, "upload_too_large")
    broken = production.post(
        "/api/v1/documents/receipts", json={"filename": "x.jpg", "file_base64": "no es base64!"}
    )
    assert (broken.status_code, broken.json()["code"]) == (422, "upload_invalid")


def test_expense_with_receipt_can_be_viewed_replaced_and_removed() -> None:
    world = build_org("a")
    _approved(world)
    production = logged_in(world.members[Role.PRODUCTION])
    receipt = _ok(_upload(production, JPEG, "factura flete.jpg"), 201)
    data = _ok(_expense(production, world, receipt_document_id=receipt["id"]), 201)
    assert data["receipts_enabled"] is True
    [expense] = [e for e in data["items"] if e["description"] == "Flete"]
    assert expense["receipt"]["id"] == receipt["id"]
    assert expense["receipt"]["filename"] == "factura flete.jpg"

    # Lo ve quien ve costos, con su tipo real y sin que el navegador lo reinterprete.
    file = production.get(f"/api/v1/expenses/{expense['id']}/receipt")
    assert file.status_code == 200
    assert file.content == JPEG
    assert file.headers["content-type"] == "image/jpeg"
    assert file.headers["x-content-type-options"] == "nosniff"
    assert "filename*=UTF-8''factura%20flete.jpg" in file.headers["content-disposition"]

    # El mismo comprobante no puede ir en dos gastos.
    reused = _expense(production, world, receipt_document_id=receipt["id"])
    assert (reused.status_code, reused.json()["code"]) == (409, "document_in_use")

    # Reemplazarlo por un PDF y después quitarlo.
    pdf = _ok(_upload(production, PDF, "factura.pdf"), 201)
    path = f"/api/v1/expenses/{expense['id']}"
    data = _ok(production.patch(path, json={"receipt_document_id": pdf["id"]}))
    [expense] = [e for e in data["items"] if e["id"] == expense["id"]]
    assert expense["receipt"]["mime"] == "application/pdf"
    # Editar otra cosa no toca el comprobante.
    data = _ok(production.patch(path, json={"description": "Flete ida"}))
    [expense] = [e for e in data["items"] if e["id"] == expense["id"]]
    assert expense["receipt"]["id"] == pdf["id"]
    data = _ok(production.patch(path, json={"receipt_document_id": None}))
    [expense] = [e for e in data["items"] if e["id"] == expense["id"]]
    assert expense["receipt"] is None
    missing = production.get(f"/api/v1/expenses/{expense['id']}/receipt")
    assert (missing.status_code, missing.json()["code"]) == (404, "receipt_not_found")


def test_receipt_must_be_a_receipt_of_the_same_org() -> None:
    world, other = build_org("a"), build_org("b")
    _approved(world)
    owner = logged_in(world.members[Role.OWNER])
    purchase_order = _ok(_upload(owner, PDF, "oc.pdf", "purchase-orders"), 201)
    wrong_kind = _expense(owner, world, receipt_document_id=purchase_order["id"])
    assert (wrong_kind.status_code, wrong_kind.json()["code"]) == (404, "document_not_found")
    foreign = _ok(_upload(logged_in(other.members[Role.OWNER]), JPEG), 201)
    stolen = _expense(owner, world, receipt_document_id=foreign["id"])
    assert (stolen.status_code, stolen.json()["code"]) == (404, "document_not_found")


def test_manual_approval_with_purchase_order_attached() -> None:
    world = build_org("a")
    manager = logged_in(world.members[Role.MANAGER])
    proposal = _send(manager, world)["proposal"]
    file = manager.get(f"/api/v1/proposals/{proposal['id']}/purchase-order")
    assert (file.status_code, file.json()["code"]) == (404, "purchase_order_not_found")

    receipt = _ok(_upload(manager, JPEG), 201)
    wrong = manager.post(
        f"/api/v1/proposals/{proposal['id']}/approve", json={"po_document_id": receipt["id"]}
    )
    assert (wrong.status_code, wrong.json()["code"]) == (404, "document_not_found")

    order = _ok(_upload(manager, PDF, "OC 4471.pdf", "purchase-orders"), 201)
    approved = _ok(
        manager.post(
            f"/api/v1/proposals/{proposal['id']}/approve",
            json={"po_number": "OC-4471", "po_document_id": order["id"]},
        )
    )
    assert approved["po_document_id"] == order["id"]
    # La ve cualquiera que vea la propuesta (por ejemplo, quien cotiza).
    quoter = logged_in(world.members[Role.QUOTER])
    file = quoter.get(f"/api/v1/proposals/{proposal['id']}/purchase-order")
    assert (file.status_code, file.content) == (200, PDF)
    assert file.headers["content-type"] == "application/pdf"


def test_without_storage_uploads_are_disabled(settings: Settings) -> None:
    world = build_org("a")
    owner = logged_in(world.members[Role.OWNER])
    settings.storage_backend = "disabled"
    assert owner.get("/api/v1/auth/me").json()["uploads_enabled"] is False
    response = _upload(owner, JPEG)
    assert (response.status_code, response.json()["code"]) == (503, "storage_disabled")
    settings.storage_backend = "local"
    assert owner.get("/api/v1/auth/me").json()["uploads_enabled"] is True


def test_documents_are_append_only_for_the_app_role() -> None:
    world = build_org("a")
    _ok(_upload(logged_in(world.members[Role.OWNER]), JPEG), 201)
    for statement in ("UPDATE documents SET filename = 'x'", "DELETE FROM documents"):
        with (
            pytest.raises(ProgrammingError, match="permission denied"),
            session_scope(DbContext(organization_id=world.organization_id)) as s,
        ):
            s.execute(text(statement))


def test_storage_settings_by_environment() -> None:
    assert Settings(env="local").storage_backend == "local"
    secret = SecretStr("x" * 40)
    # Fuera de local, sin configurar queda apagado (no rompe el deploy) y el disco no se acepta.
    assert Settings(env="production", jwt_secret=secret).storage_backend == "disabled"
    with pytest.raises(ValidationError, match="STORAGE_BACKEND=local"):
        Settings(env="production", jwt_secret=secret, storage_backend="local")
    with pytest.raises(ValidationError, match="S3_BUCKET"):
        Settings(env="production", jwt_secret=secret, storage_backend="s3", s3_bucket="b")
    configured = Settings(
        env="production",
        jwt_secret=secret,
        storage_backend="s3",
        s3_bucket="b",
        s3_access_key_id="id",
        s3_secret_access_key=SecretStr("secret"),
    )
    assert configured.storage_backend == "s3"


@pytest.fixture
def s3(settings: Settings) -> Iterator[Any]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="comprobantes-test")
        settings.storage_backend = "s3"
        settings.s3_bucket = "comprobantes-test"
        settings.s3_region = "us-east-1"
        settings.s3_access_key_id = "test"
        settings.s3_secret_access_key = SecretStr("test")
        yield client


def test_s3_storage_roundtrip(s3: Any) -> None:
    storage = get_storage()
    assert isinstance(storage, S3Storage)
    key = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b/receipt/0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5c"
    storage.put(key, JPEG, "image/jpeg")
    assert storage.get(key) == JPEG
    head = s3.head_object(Bucket="comprobantes-test", Key=key)
    assert head["ContentType"] == "image/jpeg"
    with pytest.raises(AppError) as missing:
        storage.get(key + "0")
    assert (missing.value.status, missing.value.code) == (503, "storage_unavailable")


def test_upload_and_download_through_s3(s3: Any) -> None:
    world = build_org("a")
    _approved(world)
    production = logged_in(world.members[Role.PRODUCTION])
    receipt = _ok(_upload(production, JPEG), 201)
    data = _ok(_expense(production, world, receipt_document_id=receipt["id"]), 201)
    [expense] = [e for e in data["items"] if e["description"] == "Flete"]
    assert production.get(f"/api/v1/expenses/{expense['id']}/receipt").content == JPEG
    [stored] = s3.list_objects_v2(Bucket="comprobantes-test")["Contents"]
    assert stored["Key"] == f"{world.organization_id}/receipt/{receipt['id']}"


def test_storage_keys_never_carry_user_input(tmp_path: Any) -> None:
    storage = LocalStorage(str(tmp_path))
    org = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
    for key in ("../escape", f"{org}/receipt/../../x", f"{org}/receipt/ticket.jpg", f"/{org}"):
        with pytest.raises(ValueError, match="clave"):
            storage.put(key, JPEG, "image/jpeg")
