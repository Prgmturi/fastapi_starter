from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# Free text from the IdP that reaches logs and responses (email, names):
# only control characters are refused.
_NO_CONTROL_CHARS = r"^[^\x00-\x1f\x7f]+$"


class TokenResponse(BaseModel):
    """Token response returned to client after OAuth2 code exchange or refresh."""

    access_token: str = Field(description="JWT access token")
    refresh_token: str = Field(
        description=(
            "Refresh token — internal use only, set as HttpOnly cookie by the router."
        )
    )
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(description="Access token lifetime in seconds")
    refresh_expires_in: int = Field(
        default=0,
        description="Refresh token lifetime in seconds (0 = session cookie / never)",
    )


class RoleEnum(StrEnum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    COLLAB = "collaborator"
    USER = "user"

    @classmethod
    def all_roles(cls) -> list[RoleEnum]:
        """Get all defined roles."""
        return [cls.SUPERADMIN, cls.ADMIN, cls.COLLAB, cls.USER]

    @classmethod
    def staff_roles(cls) -> list[RoleEnum]:
        """Roles with elevated privileges."""
        return [cls.SUPERADMIN, cls.ADMIN]


class User(BaseModel):
    id: str = Field(
        min_length=1, max_length=255, description="Unique user ID (from 'sub' claim)"
    )
    # The value comes from a JWT whose signature is already verified: this is
    # not where we decide which usernames a user may register (Keycloak
    # decides that), but what may travel through logs and responses without
    # harm. Only whitespace and control characters are refused (log
    # injection, CRLF in headers); everything else passes.
    #
    # The previous pattern was ^[a-zA-Z0-9_-]+$ with min_length=3: it refused
    # "mario.rossi@example.com", the preferred_username Keycloak issues as
    # soon as "Email as username" is on. Every valid login became an error.
    #
    # Note: the $ anchor holds because pydantic v2 uses rust-regex, where $
    # means the strict end of the string. With regex_engine="python-re" $
    # would accept a trailing \n, and "evil\n" would pass.
    username: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[^\s\x00-\x1f\x7f]+$",
        description="Username from the IdP (no whitespace, no control chars)",
        examples=["mario_rossi", "mario.rossi@example.com"],
    )
    # Email and names follow the same rule as username: Keycloak decides
    # what is valid, here only control characters are refused. EmailStr
    # refused reserved domains such as .local, so mario@azienda.local could
    # never log in. 320 = 64 + "@" + 255. For names 255 is Keycloak's own
    # limit: the old 100 locked out users with longer names.
    email: str | None = Field(
        default=None,
        min_length=1,
        max_length=320,
        pattern=_NO_CONTROL_CHARS,
        description="Email address from the IdP (no control chars)",
    )
    email_verified: bool = Field(default=False, description="Email verified")
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=_NO_CONTROL_CHARS,
        description="First name",
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=_NO_CONTROL_CHARS,
        description="Last name",
    )
    roles: list[RoleEnum] = Field(
        default_factory=list,
        description="User roles",
        examples=[[RoleEnum.USER, RoleEnum.ADMIN]],
    )

    @property
    def full_name(self) -> str | None:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name

    # RoleEnum is a StrEnum: a member equals its value, so "admin" matches
    # RoleEnum.ADMIN and a string that names no role matches nothing. The
    # old RoleEnum("manager") conversion raised ValueError: a 500 in a route.
    def has_role(self, role: RoleEnum | str) -> bool:
        return role in self.roles

    def has_any_role(self, roles: list[RoleEnum | str]) -> bool:
        return any(role in self.roles for role in roles)

    def has_all_roles(self, roles: list[RoleEnum | str]) -> bool:
        return all(role in self.roles for role in roles)

    def is_staff(self) -> bool:
        return any(role in self.roles for role in RoleEnum.staff_roles())
