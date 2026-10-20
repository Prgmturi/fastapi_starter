from typing import Literal

from pydantic import Field, SecretStr, computed_field, field_validator, model_validator
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
    public_url: str = Field(
        default="",
        description=(
            "Keycloak's address as the browser sees it, e.g. "
            "https://auth.example.com: the login redirect and the token issuer. "
            "Keys, tokens and logout use scheme://host:port. "
            "Empty: the same as scheme://host:port."
        ),
    )
    realm: str = Field(
        default="fastapi-starter",
        description="Keycloak realm name",
    )
    client_id: str = Field(
        default="fastapi-backend",
        description="Application Client ID",
    )
    # SecretStr: repr() and model_dump() show stars, get_secret_value() the
    # secret
    client_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Client secret (confidential client)",
    )
    allowed_clients: list[str] = Field(
        default_factory=list,
        description=(
            "Clients whose access tokens the API accepts (azp claim). "
            "Empty: only client_id."
        ),
    )
    allowed_redirect_uris: list[str] = Field(
        default_factory=list,
        description=(
            "redirect_uri values /auth/login and /auth/token accept, compared "
            "exactly. Empty: not checked here, Keycloak alone decides."
        ),
    )
    audience: str = Field(
        default="",
        description=(
            "Expected aud claim. Empty: aud is not checked. "
            "Needs an audience mapper on the Keycloak client."
        ),
    )
    jwks_cache_ttl: int = Field(
        default=3600,
        description="JWKS cache expiration in seconds",
    )
    jwks_min_refresh_interval: int = Field(
        default=30,
        description=(
            "Minimum seconds between two fetches of the signing keys: limits "
            "the calls caused by unknown kids and by retries while Keycloak "
            "is down."
        ),
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

    @field_validator("public_url")
    @classmethod
    def public_url_is_absolute(cls, value: str) -> str:
        # Without a scheme the browser would read the redirect as a path of
        # the frontend itself
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("public_url must start with http:// or https://")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_host_prefix_constraints(self) -> "KeycloakSettings":
        if self.cookie_name.startswith("__Host-"):
            if self.cookie_path != "/":
                raise ValueError("__Host- prefix requires cookie_path='/'")
            if not self.cookie_secure:
                raise ValueError("__Host- prefix requires cookie_secure=True")
        return self

    @model_validator(mode="after")
    def default_allowed_clients_to_client_id(self) -> "KeycloakSettings":
        # Without an explicit list the API accepts only the tokens issued to
        # itself. The default depends on client_id, so it is filled in here.
        if not self.allowed_clients:
            self.allowed_clients = [self.client_id]
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def server_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def public_server_url(self) -> str:
        return self.public_url or self.server_url

    @computed_field  # type: ignore[prop-decorator]
    @property
    def issuer(self) -> str:
        """The iss claim: Keycloak signs tokens with its public address."""
        return f"{self.public_server_url}/realms/{self.realm}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def token_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/token"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def auth_url(self) -> str:
        """Where the browser is sent to log in, so the public address."""
        return f"{self.issuer}/protocol/openid-connect/auth"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def certs_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/certs"
