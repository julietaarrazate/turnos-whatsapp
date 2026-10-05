import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def test_database_urls_get_the_psycopg_driver() -> None:
    settings = Settings(
        database_url="postgres://u:p@host/db?sslmode=require",
        migrator_database_url="postgresql://u:p@host/db",
    )
    assert settings.database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"
    assert settings.migrator_database_url == "postgresql+psycopg://u:p@host/db"


def test_production_requires_a_real_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(env="production")
    assert Settings(env="production", jwt_secret=SecretStr("x" * 40)).env == "production"


def test_resend_backend_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="RESEND_API_KEY"):
        Settings(env="staging", jwt_secret=SecretStr("x" * 40), email_backend="resend")
