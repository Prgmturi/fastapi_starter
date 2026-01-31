from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from fastapi_starter.core.config.base import AppSettings
from fastapi_starter.core.config.database import DatabaseSettings
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.config.server import ServerSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app: AppSettings = AppSettings()
    database: DatabaseSettings = DatabaseSettings()
    keycloak: KeycloakSettings = KeycloakSettings()
    server: ServerSettings = ServerSettings()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()



__all__ = [
    "Settings",
    "AppSettings",
    "DatabaseSettings",
    "KeycloakSettings",
    "ServerSettings",
    "get_settings",
]