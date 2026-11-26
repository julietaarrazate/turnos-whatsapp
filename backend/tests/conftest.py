"""Fixtures globales. Los tests usan un Postgres 16 real (RLS y triggers solo existen ahí).

Por defecto: base ``app_test`` en localhost (ver ``infra/postgres/init.sql``).
"""

import os
import tempfile
from collections.abc import Iterator

os.environ.setdefault("ENV", "test")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("PUSH_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_runtime@localhost:5432/app_test")
os.environ.setdefault(
    "MIGRATOR_DATABASE_URL",
    "postgresql+psycopg://app_migrator@localhost:5432/app_test",
)
# Los archivos subidos en los tests van a un directorio temporal (storage local).
os.environ.setdefault("STORAGE_LOCAL_DIR", tempfile.mkdtemp(prefix="app-storage-"))

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from app.core.config import Settings, get_settings
from app.core.rate_limit import limiter
from app.main import create_app
from app.models_registry import metadata
from app.modules.notifications import console_backend

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """En CI los tests se reparten en varias máquinas (cada una con su Postgres):
    ``TEST_SHARDS=4 TEST_SHARD=0..3``. Se reparten uno y uno (no por archivo), así la matriz de
    permisos, que es lo más largo, queda pareja entre todas."""
    shards = int(os.environ.get("TEST_SHARDS", "1"))
    shard = int(os.environ.get("TEST_SHARD", "0"))
    if shards <= 1:
        return
    keep = [item for i, item in enumerate(items) if i % shards == shard]
    drop = [item for i, item in enumerate(items) if i % shards != shard]
    config.hook.pytest_deselected(items=drop)
    items[:] = keep


@pytest.fixture(scope="session")
def migrator_engine() -> Iterator[Engine]:
    engine = create_engine(get_settings().migrator_database_url)
    yield engine
    engine.dispose()


def alembic_config(url: str) -> Config:
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.attributes["url"] = url
    return config


@pytest.fixture(scope="session", autouse=True)
def _schema(migrator_engine: Engine) -> None:
    """Esquema limpio + todas las migraciones, una vez por corrida."""
    with migrator_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(get_settings().migrator_database_url), "head")


@pytest.fixture(autouse=True)
def _clean_tables(migrator_engine: Engine) -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in metadata.sorted_tables)
    with migrator_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture(autouse=True)
def _reset_in_memory_state() -> None:
    limiter.reset()
    console_backend.sent.clear()


@pytest.fixture
def settings() -> Iterator[Settings]:
    """Settings mutables para un test; se restauran al terminar."""
    current = get_settings()
    snapshot = current.model_copy()
    yield current
    for field in Settings.model_fields:
        setattr(current, field, getattr(snapshot, field))


def make_client() -> TestClient:
    return TestClient(create_app(), headers={"X-Requested-With": "fetch"})


@pytest.fixture
def client() -> TestClient:
    return make_client()
