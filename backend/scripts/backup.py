"""Backup diario de la base: pg_dump → verificación → prueba de restore → cifrado → bucket.

Lo corre `.github/workflows/backup.yml` todos los días (~1 min de Actions, dentro de lo gratis).
Neon gratis solo deja volver 6 horas atrás; esto guarda BACKUP_KEEP_DAYS días (30).

Variables:
  BACKUP_DATABASE_URL  un rol que lee todas las filas (BYPASSRLS). En Neon, el dueño que creó la
                       consola; app_migrator y app_runtime están sujetos a RLS y no sirven.
  BACKUP_PASSPHRASE    clave del cifrado (gpg, AES-256). Sin ella, el backup no se puede abrir.
  S3_BUCKET, S3_ENDPOINT_URL, S3_REGION, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY  como la app.
  RESTORE_CHECK_URL    opcional: base vacía donde se restaura y se comparan las filas (con un rol
                       que no esté sujeto a RLS, para poder contarlas).
  RESTORE_CHECK_ROLE   opcional: rol dueño de lo restaurado (app_migrator, como en la base real).
  BACKUP_KEEP_DAYS     opcional, 30.
  PG_BINDIR            opcional: carpeta de pg_dump/pg_restore de la versión del servidor
                       (si hay varias instaladas, pg_dump 17 genera SQL que Postgres 16 no acepta).

Uso manual, sin bucket: uv run python scripts/backup.py --output /ruta/segura
Restaurar: docs/architecture/DEPLOY.md §7.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import boto3
import psycopg
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from psycopg import sql

PREFIX = "backups/"
_KEY_DATE = re.compile(r"^backups/[a-z0-9_-]+-(\d{4}-\d{2}-\d{2})\.dump\.gpg$")


class BackupError(Exception):
    """Un paso falló. El mensaje nunca incluye URLs ni claves."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    passphrase: str
    bucket: str | None
    endpoint_url: str | None
    region: str
    access_key_id: str | None
    secret_access_key: str | None
    restore_check_url: str | None
    restore_check_role: str | None
    keep_days: int

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "Settings":
        required = ("BACKUP_DATABASE_URL", "BACKUP_PASSPHRASE")
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise BackupError(f"Faltan variables: {', '.join(missing)}")
        return cls(
            database_url=_libpq_url(env["BACKUP_DATABASE_URL"]),
            passphrase=env["BACKUP_PASSPHRASE"],
            bucket=env.get("S3_BUCKET") or None,
            endpoint_url=env.get("S3_ENDPOINT_URL") or None,
            region=env.get("S3_REGION") or "auto",
            access_key_id=env.get("S3_ACCESS_KEY_ID") or None,
            secret_access_key=env.get("S3_SECRET_ACCESS_KEY") or None,
            restore_check_url=_libpq_url(env["RESTORE_CHECK_URL"])
            if env.get("RESTORE_CHECK_URL")
            else None,
            restore_check_role=env.get("RESTORE_CHECK_ROLE") or None,
            keep_days=int(env.get("BACKUP_KEEP_DAYS") or 30),
        )


def _libpq_url(url: str) -> str:
    """La URL estilo SQLAlchemy (postgresql+psycopg://) también sirve: pg_dump no la entiende."""
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", url)


def _executable(name: str) -> str | None:
    bindir = os.environ.get("PG_BINDIR")
    if bindir and name.startswith("pg_"):
        return shutil.which(name, path=bindir)
    return shutil.which(name)


def _run(args: list[str], what: str, stdin: bytes | None = None) -> bytes:
    executable = _executable(args[0])
    if executable is None:
        raise BackupError(f"No está instalado {args[0]}")
    result = subprocess.run(  # noqa: S603 (argumentos armados acá, sin shell)
        [executable, *args[1:]], input=stdin, capture_output=True, check=False
    )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip().splitlines()[-3:]
        hint = ""
        if "row-level security" in " ".join(detail):
            hint = " El rol está sujeto a RLS: usá uno con BYPASSRLS (en Neon, el dueño)."
        raise BackupError(f"{what} falló: {' | '.join(detail)}{hint}")
    return result.stdout


def row_counts(url: str) -> dict[str, int]:
    """Filas de cada tabla del esquema public (con un rol que no esté sujeto a RLS)."""
    with psycopg.connect(url) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
        ]
        counts: dict[str, int] = {}
        for table in tables:
            query = sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
            row = conn.execute(query).fetchone()
            counts[table] = int(row[0]) if row else 0
        return counts


def dump(url: str, path: Path) -> None:
    args = ["pg_dump", "--format=custom", "--no-owner", f"--dbname={url}", f"--file={path}"]
    _run(args, "pg_dump")


def verify(path: Path) -> None:
    listing = _run(["pg_restore", "--list", str(path)], "Leer el backup")
    if b"TABLE DATA public organizations" not in listing:
        raise BackupError("El backup no tiene los datos de las tablas")


def restore(path: Path, url: str, role: str | None = None) -> None:
    """Restaura en una base vacía, como en un restore real (los dueños pasan a ``role``)."""
    args = ["pg_restore", "--no-owner", "--exit-on-error", f"--dbname={url}"]
    if role:
        args.append(f"--role={role}")
    _run([*args, str(path)], "Restaurar el backup")


def check_restore(
    path: Path, url: str, role: str | None, before: dict[str, int], after: dict[str, int]
) -> int:
    """Restaura y compara las filas. Entre el antes y el después del dump pudo haber escrituras:
    lo restaurado tiene que estar entre los dos conteos, tabla por tabla."""
    restore(path, url, role)
    restored = row_counts(url)
    problems = []
    for table in sorted(set(before) | set(after)):
        low = min(before.get(table, 0), after.get(table, 0))
        high = max(before.get(table, 0), after.get(table, 0))
        if not low <= restored.get(table, -1) <= high:
            problems.append(f"{table}: {restored.get(table)} (esperado {low}–{high})")
    if problems:
        raise BackupError("El restore no coincide: " + "; ".join(problems))
    return sum(restored.values())


def encrypt(path: Path, passphrase: str) -> Path:
    out = path.with_name(path.name + ".gpg")
    args = ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback", "--symmetric"]
    args += ["--cipher-algo", "AES256", "--passphrase-fd", "0", f"--output={out}", str(path)]
    _run(args, "Cifrar", stdin=passphrase.encode())
    return out


def decrypt(path: Path, passphrase: str, out: Path) -> None:
    args = ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback", "--decrypt"]
    args += ["--passphrase-fd", "0", f"--output={out}", str(path)]
    _run(args, "Descifrar", stdin=passphrase.encode())


def s3_client(settings: Settings) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        region_name=settings.region,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.secret_access_key,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def prune(client: Any, bucket: str, today: date, keep_days: int) -> list[str]:
    """Borra los backups de más de ``keep_days`` días. Solo toca claves con el formato propio."""
    cutoff = today - timedelta(days=keep_days)
    deleted = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=PREFIX):
        for item in page.get("Contents", []):
            match = _KEY_DATE.match(item["Key"])
            if match and date.fromisoformat(match.group(1)) < cutoff:
                client.delete_object(Bucket=bucket, Key=item["Key"])
                deleted.append(item["Key"])
    return deleted


def backup_key(database_url: str, day: date) -> str:
    database = database_url.rsplit("/", 1)[-1].split("?", maxsplit=1)[0]
    name = re.sub(r"[^a-z0-9_-]", "-", database.lower())
    return f"{PREFIX}{name or 'base'}-{day.isoformat()}.dump.gpg"


def run_backup(settings: Settings, *, today: date, output: Path | None = None) -> str:
    """Hace el backup completo y devuelve un resumen. Cualquier falla es un BackupError."""
    with tempfile.TemporaryDirectory(prefix="backup-") as tmp:
        dump_path = Path(tmp) / "app.dump"
        before = row_counts(settings.database_url)
        dump(settings.database_url, dump_path)
        after = row_counts(settings.database_url)
        verify(dump_path)
        summary = [f"{len(after)} tablas, {sum(after.values())} filas"]
        if settings.restore_check_url:
            restored = check_restore(
                dump_path, settings.restore_check_url, settings.restore_check_role, before, after
            )
            summary.append(f"restore verificado ({restored} filas)")
        encrypted = encrypt(dump_path, settings.passphrase)
        key = backup_key(settings.database_url, today)
        summary.append(f"{encrypted.stat().st_size / 1024:.0f} KB cifrado")
        if output is not None:
            output.mkdir(parents=True, exist_ok=True)
            target = output / key.removeprefix(PREFIX)
            shutil.copyfile(encrypted, target)
            summary.append(f"guardado en {target}")
        if settings.bucket:
            client = s3_client(settings)
            client.put_object(Bucket=settings.bucket, Key=key, Body=encrypted.read_bytes())
            deleted = prune(client, settings.bucket, today, settings.keep_days)
            summary.append(f"subido a {key}; {len(deleted)} viejos borrados")
        elif output is None:
            raise BackupError("No hay dónde guardarlo: configurá S3_BUCKET o usá --output")
    return " · ".join(summary)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup cifrado de la base")
    parser.add_argument("--output", type=Path, help="carpeta local (además del bucket, si hay)")
    args = parser.parse_args()
    try:
        settings = Settings.from_env(dict(os.environ))
        print(run_backup(settings, today=datetime.now(UTC).date(), output=args.output))
    except BackupError as exc:
        print(f"Backup falló: {exc}", file=sys.stderr)
        return 1
    except (psycopg.Error, BotoCoreError, ClientError) as exc:
        print(f"Backup falló: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
