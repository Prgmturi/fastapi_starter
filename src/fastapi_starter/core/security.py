from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakError

from fastapi_starter.core.config import Settings, get_settings


@dataclass(frozen=True)
class CurrentUser:
    """Represents the authenticated user from Keycloak token."""

    id: str
    email: str | None
    username: str | None
    roles: tuple[str, ...]
    raw_token: dict[str, Any]

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        """Check if user has any of the specified roles."""
        return any(role in self.roles for role in roles)

    def has_all_roles(self, *roles: str) -> bool:
        """Check if user has all of the specified roles."""
        return all(role in self.roles for role in roles)


class KeycloakAuth:
    """Handles Keycloak authentication and token validation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._keycloak: KeycloakOpenID | None = None
        self._public_key: str | None = None

    @property
    def keycloak(self) -> KeycloakOpenID:
        """Get or create the Keycloak client."""
        if self._keycloak is None:
            self._keycloak = KeycloakOpenID(
                server_url=self._settings.keycloak_url,
                client_id=self._settings.keycloak_client_id,
                realm_name=self._settings.keycloak_realm,
                client_secret_key=self._settings.keycloak_client_secret or None,
            )
        return self._keycloak

    async def get_public_key(self) -> str:
        """Get the Keycloak realm public key for JWT validation."""
        if self._public_key is None:
            raw_key = self.keycloak.public_key()
            self._public_key = (
                f"-----BEGIN PUBLIC KEY-----\n{raw_key}\n-----END PUBLIC KEY-----"
            )
        return self._public_key

    async def validate_token(self, token: str) -> dict[str, Any]:
        """Validate a JWT token and return the decoded payload."""
        try:
            public_key = await self.get_public_key()
            payload: dict[str, Any] = self.keycloak.decode_token(
                token,
                key=public_key,
                options={
                    "verify_signature": True,
                    "verify_aud": False,
                    "verify_exp": True,
                },
            )
            return payload
        except KeycloakError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token validation failed: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

    def extract_user(self, token_payload: dict[str, Any]) -> CurrentUser:
        """Extract user information from token payload."""
        # Extract roles from realm_access
        realm_access = token_payload.get("realm_access", {})
        roles = tuple(realm_access.get("roles", []))

        return CurrentUser(
            id=token_payload.get("sub", ""),
            email=token_payload.get("email"),
            username=token_payload.get("preferred_username"),
            roles=roles,
            raw_token=token_payload,
        )


# Security scheme
bearer_scheme = HTTPBearer(auto_error=True)

# Global auth instance
_keycloak_auth: KeycloakAuth | None = None


def get_keycloak_auth() -> KeycloakAuth:
    """Get the global Keycloak auth instance."""
    global _keycloak_auth
    if _keycloak_auth is None:
        _keycloak_auth = KeycloakAuth(get_settings())
    return _keycloak_auth


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    auth: Annotated[KeycloakAuth, Depends(get_keycloak_auth)],
) -> CurrentUser:
    """Dependency to get the current authenticated user."""
    token_payload = await auth.validate_token(credentials.credentials)
    return auth.extract_user(token_payload)


async def get_current_user_optional(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(auto_error=False)),
    ],
    auth: Annotated[KeycloakAuth, Depends(get_keycloak_auth)],
) -> CurrentUser | None:
    """Dependency to optionally get the current user (no error if not authenticated)."""
    if credentials is None:
        return None
    token_payload = await auth.validate_token(credentials.credentials)
    return auth.extract_user(token_payload)


def require_roles(*required_roles: str) -> Any:
    """Create a dependency that requires specific roles."""

    async def role_checker(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if not user.has_any_role(*required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {', '.join(required_roles)}",
            )
        return user

    return Depends(role_checker)


# Type aliases for dependency injection
AuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
OptionalUser = Annotated[CurrentUser | None, Depends(get_current_user_optional)]
