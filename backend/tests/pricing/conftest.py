"""El motor es puro: sus tests no necesitan base de datos (anula las fixtures globales)."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    return None


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    return None
