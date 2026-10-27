from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fastapi_starter.core.config.app import AppSettings
from fastapi_starter.core.config.auth_cookie import AuthCookieSettings
from fastapi_starter.core.config.database import DatabaseSettings
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.config.production import production_problems
from fastapi_starter.core.config.server import ServerSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    auth_cookie: AuthCookieSettings = Field(default_factory=AuthCookieSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    keycloak: KeycloakSettings = Field(default_factory=KeycloakSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)

    @model_validator(mode="after")
    def refuse_development_values_in_production(self) -> "Settings":
        # All problems in one error: a deploy should not need one restart
        # per mistake
        if self.app.is_production:
            problems = production_problems(
                self.app, self.auth_cookie, self.database, self.keycloak, self.server
            )
            if problems:
                raise ValueError(
                    "refusing to start in production:\n"
                    + "\n".join(f"- {problem}" for problem in problems)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


__all__ = [
    "Settings",
    "AppSettings",
    "AuthCookieSettings",
    "DatabaseSettings",
    "KeycloakSettings",
    "ServerSettings",
    "get_settings",
]
