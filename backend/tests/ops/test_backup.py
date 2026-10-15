"""Backup diario (scripts/backup.py): dump, restore de prueba, cifrado, subida y retención.

Usa el Postgres de los tests: lee como superusuario (no sujeto a RLS, como el dueño de Neon) y
restaura en bases descartables.
"""

import importlib.util
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import boto3
import psycopg
import pytest
from moto import mock_aws

from tests.security.harness import build_org

_SPEC = importlib.util.spec_from_file_location(
    "backup_script", Path(__file__).resolve().parents[2] / "scripts" / "backup.py"
)
assert _SPEC
assert _SPEC.loader
backup = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(backup)

SERVER = os.environ.get("BACKUP_TEST_SERVER_URL", "postgresql://postgres@localhost:5432")
SOURCE = f"{SERVER}/app_test"
BUCKET = "backups-test"
TODAY = date(2026, 10, 15)


def _recreate(name: str, owner: str = "app_migrator") -> str:
    with psycopg.connect(f"{SERVER}/postgres", autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{name}" OWNER {owner}')
    return f"{SERVER}/{name}"


def _drop(name: str) -> None:
    with psycopg.connect(f"{SERVER}/postgres", autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def check_db() -> Iterator[str]:
    yield _recreate("backup_check")
    _drop("backup_check")


@pytest.fixture
def s3() -> Iterator[Any]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def _settings(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "database_url": SOURCE,
        "passphrase": "clave-de-prueba",
        "bucket": None,
        "endpoint_url": None,
        "region": "us-east-1",
        "access_key_id": "test",
        "secret_access_key": "test",
        "restore_check_url": None,
        "restore_check_role": None,
        "keep_days": 30,
    }
    return backup.Settings(**{**values, **overrides})


def test_backup_is_verified_encrypted_uploaded_and_pruned(
    check_db: str, s3: Any, tmp_path: Path
) -> None:
    build_org("a")
    # Uno viejo (se borra), uno reciente (queda) y algo que no es un backup (no se toca).
    for key in ("backups/app_test-2026-08-01.dump.gpg", "backups/app_test-2026-10-01.dump.gpg"):
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"x")
    s3.put_object(Bucket=BUCKET, Key="backups/notas.txt", Body=b"x")

    summary = backup.run_backup(
        _settings(bucket=BUCKET, restore_check_url=check_db, restore_check_role="app_migrator"),
        today=TODAY,
    )
    assert "restore verificado" in summary
    keys = {o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"]}
    assert keys == {
        "backups/app_test-2026-10-01.dump.gpg",
        "backups/app_test-2026-10-15.dump.gpg",
        "backups/notas.txt",
    }

    # Cifrado: sin la clave no se abre; con la clave es un dump que pg_restore lee.
    encrypted = tmp_path / "bajado.dump.gpg"
    body = s3.get_object(Bucket=BUCKET, Key="backups/app_test-2026-10-15.dump.gpg")["Body"]
    encrypted.write_bytes(body.read())
    assert b"organizations" not in encrypted.read_bytes()
    with pytest.raises(backup.BackupError, match="Descifrar"):
        backup.decrypt(encrypted, "otra-clave", tmp_path / "no.dump")
    backup.decrypt(encrypted, "clave-de-prueba", tmp_path / "app.dump")
    backup.verify(tmp_path / "app.dump")


def test_documented_restore_keeps_rls_and_app_permissions(tmp_path: Path) -> None:
    """El restore de DEPLOY §7: como app_migrator en una base nueva, sin flags especiales."""
    build_org("a")
    backup.run_backup(_settings(), today=TODAY, output=tmp_path)
    encrypted = tmp_path / "app_test-2026-10-15.dump.gpg"
    backup.decrypt(encrypted, "clave-de-prueba", tmp_path / "a.dump")
    target = _recreate("backup_restore")
    try:
        migrator_url = target.replace("postgres@", "app_migrator@")
        backup.restore(tmp_path / "a.dump", migrator_url)
        assert backup.row_counts(target) == backup.row_counts(SOURCE)
        with psycopg.connect(target) as conn:
            forced = conn.execute(
                "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'expenses'"
            ).fetchone()
            readable = conn.execute(
                "SELECT has_table_privilege('app_runtime', 'expenses', 'SELECT')"
            ).fetchone()
            owner = conn.execute(
                "SELECT tableowner FROM pg_tables WHERE tablename = 'expenses'"
            ).fetchone()
        assert forced == (True,)
        assert readable == (True,)
        assert owner == ("app_migrator",)
    finally:
        _drop("backup_restore")


def test_role_subject_to_rls_gets_a_clear_error(tmp_path: Path) -> None:
    build_org("a")
    rls_role = SOURCE.replace("postgres@", "app_migrator@")
    with pytest.raises(backup.BackupError, match="BYPASSRLS"):
        backup.run_backup(_settings(database_url=rls_role), today=TODAY, output=tmp_path)


def test_restore_check_detects_missing_rows(check_db: str, tmp_path: Path) -> None:
    build_org("a")
    dump = tmp_path / "app.dump"
    backup.dump(SOURCE, dump)
    counts = backup.row_counts(SOURCE)
    inflated = {**counts, "organizations": counts["organizations"] + 5}
    with pytest.raises(backup.BackupError, match="organizations"):
        backup.check_restore(dump, check_db, "app_migrator", inflated, inflated)


def test_settings_from_env() -> None:
    with pytest.raises(backup.BackupError, match="BACKUP_PASSPHRASE"):
        backup.Settings.from_env({"BACKUP_DATABASE_URL": SOURCE})
    settings = backup.Settings.from_env(
        {
            "BACKUP_DATABASE_URL": "postgresql+psycopg://u:p@host/app?sslmode=require",
            "BACKUP_PASSPHRASE": "x",
            "S3_BUCKET": "",
        }
    )
    assert settings.database_url == "postgresql://u:p@host/app?sslmode=require"
    assert (settings.bucket, settings.region, settings.keep_days) == (None, "auto", 30)
    with pytest.raises(backup.BackupError, match="No hay dónde"):
        backup.run_backup(_settings(database_url=SOURCE), today=TODAY)


def test_backup_key_uses_the_database_name() -> None:
    assert (
        backup.backup_key("postgresql://u:p@host/app?sslmode=require", TODAY)
        == "backups/app-2026-10-15.dump.gpg"
    )
