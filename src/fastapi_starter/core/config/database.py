from pydantic import Field, computed_field
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
    password: str = Field(
        default="postgres",
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
    echo: bool = Field(
        default=False,
        description="Log SQL queries",
    )

    @computed_field
    @property
    def url(self) -> str:
        return (
            f"{self.driver}://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @computed_field
    @property
    def url_safe(self) -> str:
        return f"{self.driver}://{self.user}:***@{self.host}:{self.port}/{self.name}"
