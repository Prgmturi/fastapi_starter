from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(
        default="0.0.0.0",
        description="Host su cui ascoltare",
    )
    port: int = Field(
        default=8000,
        description="Porta su cui ascoltare",
    )
    workers: int = Field(
        default=1,
        description="Numero di worker processes",
    )
    timeout_keep_alive: int = Field(
        default = 5,
        description="timeout keep alive"
    )
    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Origini permesse per CORS",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Permetti credentials in CORS",
    )
    cors_allow_methods: list[str] = Field(
        default=["*"],
        description="Metodi HTTP permessi",
    )
    cors_allow_headers: list[str] = Field(
        default=["*"],
        description="Headers permessi",
    )
