from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "Plataforma productoras"
    app_base_url: str = "http://localhost:3000"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Rol de runtime: no es dueño de las tablas y está sujeto a RLS.
    database_url: str = "postgresql+psycopg://app_runtime:app_runtime@localhost:5432/app"
    # Rol dueño del esquema: solo para migraciones y tareas administrativas.
    migrator_database_url: str = "postgresql+psycopg://app_migrator:app_migrator@localhost:5432/app"


@lru_cache
def get_settings() -> Settings:
    return Settings()
