from typing import Any

from pydantic import BaseModel, EmailStr, Field
from pydantic import ValidationError as PydanticValidationError

from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.core.exceptions import UnauthorizedError
from fastapi_starter.core.logging import get_logger

logger = get_logger(__name__)


class TokenPayload(BaseModel):
    """Keycloak-specific JWT payload.

    Implementation detail of KeycloakClaimExtractor.
    """

    sub: str = Field(description="Subject - unique user ID in Keycloak")
    exp: int = Field(description="Expiration timestamp")
    iat: int = Field(description="Issued at timestamp")
    iss: str = Field(description="Issuer - Keycloak realm URL")
    aud: str | list[str] | None = Field(
        default=None, description="Audience - intended recipient"
    )

    # User info (Keycloak standard claims)
    preferred_username: str | None = Field(default=None, description="Username")
    email: EmailStr | None = Field(default=None, description="User email")
    email_verified: bool = Field(default=False, description="Email verified flag")
    given_name: str | None = Field(default=None, description="First name")
    family_name: str | None = Field(default=None, description="Last name")

    # Keycloak-specific role structures
    realm_access: dict[str, Any] | None = Field(
        default=None, description="Realm-level roles"
    )
    resource_access: dict[str, Any] | None = Field(
        default=None, description="Client-level roles"
    )


class KeycloakClaimExtractor:
    """
    Maps Keycloak JWT claims to the domain User model.

    Handles Keycloak-specific claim structure:
    - realm_access.roles for realm-level roles
    - resource_access[client_id].roles for client-level roles
    - preferred_username, given_name, family_name for user info

    To support a different provider (Auth0, Okta, etc.), write a new
    ClaimExtractor implementation — this class stays unchanged.
    """

    def __init__(self, client_id: str) -> None:
        self._client_id = client_id

    def extract_user(self, claims: dict[str, Any]) -> User:
        """
        Extract domain User from raw JWT claims dict.

        Raises:
            UnauthorizedError: If claims cannot be parsed as a valid Keycloak payload.
        """
        try:
            payload = TokenPayload.model_validate(claims)
        except PydanticValidationError as e:
            logger.warning("claim_extraction_failed", error=str(e))
            raise UnauthorizedError("Invalid token format") from e

        roles = self._collect_roles(payload)

        return User(
            id=payload.sub,
            username=payload.preferred_username or payload.sub,
            email=payload.email,
            email_verified=payload.email_verified,
            first_name=payload.given_name,
            last_name=payload.family_name,
            roles=roles,
        )

    def _collect_roles(self, payload: TokenPayload) -> list[RoleEnum]:
        """Collect roles from realm_access and resource_access, deduped."""
        role_strings: list[str] = []

        if payload.realm_access and "roles" in payload.realm_access:
            role_strings.extend(payload.realm_access["roles"])

        if payload.resource_access and self._client_id in payload.resource_access:
            client_roles = payload.resource_access[self._client_id].get("roles", [])
            role_strings.extend(client_roles)

        unique_roles = list(dict.fromkeys(role_strings))

        result: list[RoleEnum] = []
        for role_str in unique_roles:
            try:
                result.append(RoleEnum(role_str))
            except ValueError:
                logger.debug("unknown_role_skipped", role=role_str)

        return result
