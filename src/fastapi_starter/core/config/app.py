from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def installed_version() -> str:
    """The installed package's version: pyproject.toml, bumped at each release."""
    try:
        return package_version("fastapi_starter")
    except PackageNotFoundError:
        # Source on PYTHONPATH, never installed: say so rather than guess
        return "unknown"


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # A failed check prints its input, which holds lines of .env: the
        # error would show their values, secrets included
        hide_input_in_errors=True,
    )

    name: str = Field(default="fastapi_starter", description="Application name")
    version: str = Field(
        default_factory=installed_version,
        description="Application version. Unset: the installed package's",
    )
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Execution environment"
    )
    debug: bool = Field(default=False, description="Debug mode")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level, in any case"
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def log_level_in_capitals(cls, value: object) -> object:
        # APP_LOG_LEVEL=debug is as clear as DEBUG; anything else is refused
        return value.upper() if isinstance(value, str) else value

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"
