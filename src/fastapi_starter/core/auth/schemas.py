from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field


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


class AccessTokenResponse(BaseModel):
    """Public API response for token endpoints.

    Excludes refresh_token — that is delivered exclusively via HttpOnly cookie.
    """

    access_token: str = Field(description="JWT access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(description="Access token lifetime in seconds")


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
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username (3-50 chars, alphanumeric + _ -)",
        examples=["mario_rossi", "e37e9825-ac1c-4bd3-8380-579af43eac4823"],
    )
    email: EmailStr | None = Field(
        default=None, description="Email address (validated format)"
    )
    email_verified: bool = Field(default=False, description="Email verified")
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="First name",
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
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

    def has_role(self, role: RoleEnum | str) -> bool:
        if isinstance(role, str):
            role = RoleEnum(role)
        return role in self.roles

    def has_any_role(self, roles: list[RoleEnum | str]) -> bool:
        role_enums = [RoleEnum(r) if isinstance(r, str) else r for r in roles]
        return any(role in self.roles for role in role_enums)

    def has_all_roles(self, roles: list[RoleEnum | str]) -> bool:
        role_enums = [RoleEnum(r) if isinstance(r, str) else r for r in roles]
        return all(role in self.roles for role in role_enums)

    def is_staff(self) -> bool:
        return any(role in self.roles for role in RoleEnum.staff_roles())
