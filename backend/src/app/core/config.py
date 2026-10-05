from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-insecure-secret-change-me-dev-insecure-secret"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "Plataforma productoras"
    # URL pública del frontend (links de emails) y orígenes aceptados en mutaciones.
    app_base_url: str = "http://localhost:3000"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Rol de runtime: no es dueño de las tablas y está sujeto a RLS.
    database_url: str = "postgresql+psycopg://app_runtime:app_runtime@localhost:5432/app"
    # Rol dueño del esquema: solo para migraciones y tareas administrativas.
    migrator_database_url: str = "postgresql+psycopg://app_migrator:app_migrator@localhost:5432/app"

    # Auth
    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    # Ventana en la que reusar un refresh token se considera concurrencia (dos pestañas)
    # y no robo. Fuera de la ventana, el reuso revoca la sesión entera.
    refresh_reuse_grace_seconds: int = 15
    invitation_ttl_hours: int = 72
    password_reset_ttl_minutes: int = 60
    cookie_secure: bool = True

    # Email
    email_backend: Literal["console", "resend"] = "console"
    email_from: str = "Plataforma <notificaciones@example.com>"
    resend_api_key: SecretStr | None = None

    rate_limit_enabled: bool = True

    @model_validator(mode="after")
    def _check_production_secrets(self) -> Self:
        if self.env in ("staging", "production"):
            secret = self.jwt_secret.get_secret_value()
            if secret == _DEV_JWT_SECRET or len(secret) < 32:
                raise ValueError("JWT_SECRET debe configurarse (>= 32 caracteres) fuera de local")
            if self.email_backend == "resend" and self.resend_api_key is None:
                raise ValueError("RESEND_API_KEY es obligatorio con EMAIL_BACKEND=resend")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
