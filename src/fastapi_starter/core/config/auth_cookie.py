from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthCookieSettings(BaseSettings):
    """The HttpOnly cookie that carries the refresh token.

    The cookie is the app's: Keycloak never sees it. Until 0.8.0 these
    settings were part of KeycloakSettings, as KEYCLOAK_COOKIE_*.
    """

    model_config = SettingsConfigDict(
        env_prefix="AUTH_COOKIE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = Field(
        default="__Host-rt",
        description=(
            "Name of the refresh token cookie. The '__Host-' prefix makes the "
            "browser demand Secure and Path=/, and refuse a Domain."
        ),
    )
    secure: bool = Field(
        default=True,
        description="Secure flag of the cookie. Disable only in development.",
    )
    samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        description="SameSite policy of the cookie.",
    )
    path: str = Field(
        default="/",
        description="The browser sends the cookie only under this path.",
    )

    # The names before 0.8.0, read only to refuse them: ignored, an old name
    # would change the cookie without a word. The alias is the variable read.
    old_name: str | None = Field(
        default=None, validation_alias="KEYCLOAK_COOKIE_NAME", exclude=True
    )
    old_secure: str | None = Field(
        default=None, validation_alias="KEYCLOAK_COOKIE_SECURE", exclude=True
    )
    old_samesite: str | None = Field(
        default=None, validation_alias="KEYCLOAK_COOKIE_SAMESITE", exclude=True
    )
    old_path: str | None = Field(
        default=None, validation_alias="KEYCLOAK_COOKIE_PATH", exclude=True
    )

    @model_validator(mode="after")
    def refuse_names_before_0_8_0(self) -> "AuthCookieSettings":
        old_values = {
            "KEYCLOAK_COOKIE_NAME": self.old_name,
            "KEYCLOAK_COOKIE_SECURE": self.old_secure,
            "KEYCLOAK_COOKIE_SAMESITE": self.old_samesite,
            "KEYCLOAK_COOKIE_PATH": self.old_path,
        }
        found = [
            f"{old} is now {old.replace('KEYCLOAK_', 'AUTH_')}"
            for old, value in old_values.items()
            if value is not None
        ]
        if found:
            raise ValueError(
                "the refresh cookie settings have new names since 0.8.0, "
                "rename them in .env or in the environment: " + "; ".join(found)
            )
        return self

    @model_validator(mode="after")
    def follow_the_host_prefix(self) -> "AuthCookieSettings":
        # The browser drops a __Host- cookie that breaks these rules: the
        # login would seem to work and every refresh would answer 401
        if self.name.startswith("__Host-"):
            if self.path != "/":
                raise ValueError(
                    "AUTH_COOKIE_NAME starts with __Host-, which requires "
                    "AUTH_COOKIE_PATH=/"
                )
            if not self.secure:
                raise ValueError(
                    "AUTH_COOKIE_NAME starts with __Host-, which requires "
                    "AUTH_COOKIE_SECURE=true"
                )
        return self
