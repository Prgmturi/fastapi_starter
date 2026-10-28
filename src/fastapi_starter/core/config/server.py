from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # A failed check prints its input, which holds lines of .env: the
        # error would show their values, secrets included
        hide_input_in_errors=True,
    )

    host: str = Field(
        default="0.0.0.0",
        description="Host to listen on",
    )
    port: int = Field(
        default=8000,
        description="Port to listen on",
    )
    workers: int = Field(
        default=1,
        description="Number of worker processes",
    )
    timeout_keep_alive: int = Field(
        default=5,
        description="Keep-alive timeout in seconds",
    )
    # Without a limit uvicorn waits for every open request, docker stop
    # kills the process after 10 seconds, and the lifespan never closes the
    # database pool. Keep it below the stop timeout of the container.
    timeout_graceful_shutdown: int = Field(
        default=5,
        gt=0,
        description="Seconds open requests get to finish when the process stops",
    )
    forwarded_allow_ips: list[str] = Field(
        default=["127.0.0.1"],
        description="Proxies (addresses or networks) whose X-Forwarded-For "
        "uvicorn trusts for the client address",
    )
    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests",
    )
    cors_allow_methods: list[str] = Field(
        default=["*"],
        description="Allowed HTTP methods for CORS",
    )
    cors_allow_headers: list[str] = Field(
        default=["*"],
        description="Allowed headers for CORS",
    )
    max_body_size: int = Field(
        default=64 * 1024,
        gt=0,
        description="Largest request body in bytes; a larger one gets 413",
    )
    # Host validation
    trusted_hosts: list[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Allowed Host headers (TrustedHostMiddleware)",
    )
