from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class KeycloakSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KEYCLOAK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(
        default="localhost",
        description="Keycloak host",
    )
    port: int = Field(
        default=8080,
        description="Keycloak service port",
    )
    scheme: str = Field(
        default="http",
        description="URL scheme (http or https)",
    )
    realm: str = Field(
        default="fastapi-starter",
        description="Keycloak realm name",
    )
    client_id: str = Field(
        default="fastapi-backend",
        description="Application Client ID",
    )
    client_secret: str = Field(
        default="",
        description="Client secret (confidential client)",
    )
    jwks_cache_ttl: int = Field(
        default=3600,
        description="JWKS cache expiration in seconds",
    )
    request_timeout: int = Field(
        default=30,
        description="Request timeout to fetch fresh keys from Keycloak",
    )
    cookie_name: str = Field(
        default="__Host-rt",
        description=(
            "HttpOnly cookie name for the refresh token. "
            "The '__Host-' prefix enforces Secure, Path=/, no Domain at browser level."
        ),
    )
    cookie_secure: bool = Field(
        default=True,
        description="""Set Secure flag on the refresh token cookie.
        Disable only in development.""",
    )
    cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        description="SameSite policy for the refresh token cookie.",
    )
    cookie_path: str = Field(
        default="/",
        description=(
            "Path scope for the refresh token cookie. "
            "Browser sends it only to this path prefix."
        ),
    )

    @model_validator(mode="after")
    def validate_host_prefix_constraints(self) -> "KeycloakSettings":
        if self.cookie_name.startswith("__Host-"):
            if self.cookie_path != "/":
                raise ValueError("__Host- prefix requires cookie_path='/'")
            if not self.cookie_secure:
                raise ValueError("__Host- prefix requires cookie_secure=True")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def server_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def token_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/token"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def auth_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/auth"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def certs_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/certs"
