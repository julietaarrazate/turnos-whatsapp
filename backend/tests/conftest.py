"""Fixtures globales. Los tests usan un Postgres 16 real (RLS y triggers solo existen ahí).

Por defecto: base ``app_test`` en localhost (ver ``infra/postgres/init.sql``).
"""

import os
from collections.abc import Iterator

os.environ.setdefault("ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://app_runtime:app_runtime@localhost:5432/app_test"
)
os.environ.setdefault(
    "MIGRATOR_DATABASE_URL",
    "postgresql+psycopg://app_migrator:app_migrator@localhost:5432/app_test",
)

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings
from app.models_registry import metadata

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
