from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    driver: str = Field(
        default="postgresql+asyncpg",
        description="Database driver (e.g. postgresql+asyncpg)",
    )
    host: str = Field(
        default="localhost",
        description="Database host",
    )
    port: int = Field(
        default=5432,
        description="Database port",
    )
    name: str = Field(
        default="appbase",
        description="Database name",
    )
    user: str = Field(
        default="postgres",
        description="Database username",
    )
    # SecretStr: repr() and model_dump() show stars, get_secret_value() the
    # password
    password: SecretStr = Field(
        default=SecretStr("postgres"),
        description="Database password",
    )

    # Pool settings
    pool_size: int = Field(
        default=5,
        description="Number of pool connections",
    )
    pool_max_overflow: int = Field(
        default=10,
        description="Max overflow connections beyond pool_size",
    )
    pool_timeout: int = Field(
        default=5,
        description="Connection acquisition timeout in seconds",
    )
    pool_recycle: int = Field(
        default=1800,
        description="Recycle connections older than this (seconds)",
    )

    # Timeouts, for the app's engine only: the one in alembic/env.py has
    # none, so a long migration is not cut short.
    connect_timeout: float = Field(
        default=5.0,
        gt=0,
        description="Seconds to open a connection, login included",
    )
    command_timeout: float = Field(
        default=30.0,
        gt=0,
        description="Seconds a query may run; then Postgres cancels it",
    )
    echo: bool = Field(
        default=False,
        description="Log SQL queries",
    )
