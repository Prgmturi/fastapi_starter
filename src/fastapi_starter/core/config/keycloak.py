from pydantic import Field, computed_field
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

    @computed_field
    @property
    def server_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    @computed_field
    @property
    def token_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/token"

    @computed_field
    @property
    def auth_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/auth"

    @computed_field
    @property
    def certs_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/certs"
