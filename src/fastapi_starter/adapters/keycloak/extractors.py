from typing import Any

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.core.exceptions import UnauthorizedError
from fastapi_starter.core.logging import get_logger

logger = get_logger(__name__)

# Keycloak gives every user of the realm offline_access, uma_authorization
# and the composite role default-roles-<realm>. They are not ours, and every
# token carries them: a line for them would come with every request.
KEYCLOAK_DEFAULT_ROLES = frozenset({"offline_access", "uma_authorization"})
KEYCLOAK_DEFAULT_ROLE_PREFIX = "default-roles-"


def is_keycloak_default_role(role: str) -> bool:
    if role in KEYCLOAK_DEFAULT_ROLES:
        return True
    return role.startswith(KEYCLOAK_DEFAULT_ROLE_PREFIX)


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
    email: str | None = Field(default=None, description="User email")
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
        # Unknown roles already logged. One warning per role is enough to
        # notice a role written wrong in Keycloak, and realm roles are
        # shared with the other apps of the realm: a warning for theirs on
        # every request would bury everything else.
        self._reported_roles: set[str] = set()

    def extract_user(self, claims: dict[str, Any]) -> User:
        """
        Extract domain User from raw JWT claims dict.

        Raises:
            UnauthorizedError: If claims cannot be parsed as a valid Keycloak payload.
        """
        # The try covers the whole mapping from claims to User, not only the
        # first model_validate. User(...) validates too (username, email,
        # lengths), and it used to sit outside the try: a correctly signed
        # token with claims we cannot map left as a bare ValidationError,
        # that is a 500. A token we cannot read is an authentication failure
        # (401), never a fault of the server.
        try:
            payload = TokenPayload.model_validate(claims)
            roles = self._collect_roles(payload)

            return User(
                id=payload.sub,
                username=payload.preferred_username or payload.sub,
                # An empty claim is a field the user never filled in: absent,
                # not a reason to refuse the login.
                email=payload.email or None,
                email_verified=payload.email_verified,
                first_name=payload.given_name or None,
                last_name=payload.family_name or None,
                roles=roles,
            )
        except PydanticValidationError as e:
            logger.warning("claim_extraction_failed", error=str(e))
            raise UnauthorizedError("Invalid token format") from e

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
                self._report_unknown_role(role_str)

        return result

    def _report_unknown_role(self, role: str) -> None:
        """Warn the first time a role shows up, unless Keycloak gives it to all."""
        if is_keycloak_default_role(role) or role in self._reported_roles:
            return
        self._reported_roles.add(role)
        logger.warning("unknown_role_skipped", role=role)
