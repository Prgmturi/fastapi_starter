from enum import Enum
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class RoleEnum(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    COLLAB = "collaborator"
    USER = "user"

    @classmethod
    def all(cls) -> list[str]:
        """Get all defined roles."""
        return [cls.SUPERADMIN, cls.ADMIN, cls.COLLAB, cls.USER]

    @classmethod
    def staff(cls) -> list[str]:
        """Roles with elevated privileges."""
        return [cls.SUPERADMIN, cls.ADMIN]


class TokenPayload(BaseModel):
    sub: str = Field(description="Subject - unique user ID in Keycloak")
    exp: int = Field(description="Expiration timestamp")
    iat: int = Field(description="Issued at timestamp")
    iss: str = Field(description="Issuer - Keycloak realm URL")
    aud: str | list[str] | None = Field(
        default=None, description="Audience - intended recipient"
    )

    # User info
    preferred_username: str | None = Field(default=None, description="Username")
    email: str | None = Field(default=None, description="User email")
    email_verified: bool = Field(default=False, description="Email verified flag")
    given_name: str | None = Field(default=None, description="First name")
    family_name: str | None = Field(default=None, description="Last name")

    # Roles from Keycloak
    realm_access: dict[str, Any] | None = Field(
        default=None, description="Realm-level roles"
    )
    resource_access: dict[str, Any] | None = Field(
        default=None, description="Client-level roles"
    )


class User(BaseModel):
    id: str = Field(
        min_length=1, max_length=255, description="Unique user ID (from 'sub' claim)"
    )
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username (3-50 chars, alphanumeric + _ -)",
        examples=["mario_rossi", "user-123"],
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
        return any(role in self.roles for role in RoleEnum.staff())
