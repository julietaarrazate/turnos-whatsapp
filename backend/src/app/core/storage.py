"""Object storage de archivos subidos (D-17): bucket S3-compatible privado o, en desarrollo, disco.

Los archivos pasan por la API (se validan antes de guardarse) y se descargan por la API (con
el permiso de la entidad dueña): el bucket nunca se expone, no hay URLs públicas ni CORS que
configurar. Las claves no llevan nada que venga del usuario.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.errors import AppError, ensure

_KEY = re.compile(r"^[0-9a-f-]+(/[0-9a-z_-]+)*$")


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...


def _check_key(key: str) -> str:
    if not _KEY.match(key):
        raise ValueError(f"clave de storage inválida: {key!r}")
    return key


def _unavailable(exc: Exception) -> AppError:
    error = AppError(503, "storage_unavailable", "No se pudo acceder a los archivos. Reintentá.")
    error.__cause__ = exc
    return error


class LocalStorage:
    """Solo desarrollo y tests: un directorio del disco."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self.root / _check_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        try:
            return (self.root / _check_key(key)).read_bytes()
        except FileNotFoundError as exc:
            raise _unavailable(exc) from exc


class S3Storage:
    """Cloudflare R2 o AWS S3 (misma API). Se cambia de proveedor por configuración."""

    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=_check_key(key), Body=data, ContentType=content_type
            )
        except (BotoCoreError, ClientError) as exc:
            raise _unavailable(exc) from exc

    def get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_check_key(key))
            return bytes(response["Body"].read())
        except (BotoCoreError, ClientError) as exc:
            raise _unavailable(exc) from exc


@lru_cache(maxsize=4)
def _s3(bucket: str, endpoint_url: str | None, region: str, key_id: str, secret: str) -> S3Storage:
    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url or None,  # vacío: AWS S3
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )
    return S3Storage(client, bucket)


def get_storage() -> Storage | None:
    """El storage configurado, o None si los archivos están deshabilitados."""
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalStorage(settings.storage_local_dir)
    if settings.storage_backend == "s3":
        return _s3(
            ensure(settings.s3_bucket, "S3_BUCKET"),
            settings.s3_endpoint_url,
            settings.s3_region,
            ensure(settings.s3_access_key_id, "S3_ACCESS_KEY_ID"),
            ensure(settings.s3_secret_access_key, "S3_SECRET_ACCESS_KEY").get_secret_value(),
        )
    return None


def require_storage() -> Storage:
    storage = get_storage()
    if storage is None:
        raise AppError(
            503,
            "storage_disabled",
            "Todavía no está configurado dónde guardar archivos (ver docs/architecture/DEPLOY.md)",
        )
    return storage
