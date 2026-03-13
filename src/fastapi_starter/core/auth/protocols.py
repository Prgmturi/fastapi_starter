from typing import Any, Protocol, runtime_checkable

from fastapi_starter.core.auth.schemas import TokenResponse, User
from fastapi_starter.core.protocols import HealthCheckable, KeyProvider


@runtime_checkable
class TokenDecoder(Protocol):
    """Decodes and cryptographically verifies a JWT token.

    Implementations must:
    - Verify signature, expiry, and issuer
    - Raise UnauthorizedError on any failure (no library-specific exceptions leak out)
    - Return raw claims dict on success
    """

    async def decode(self, token: str) -> dict[str, Any]: ...


@runtime_checkable
class ClaimExtractor(Protocol):
    """Maps provider-specific JWT claims to the domain User model.

    Each auth provider (Keycloak, Auth0, Okta, ...) has a different claim
    structure. Implement this Protocol once per provider.
    """

    def extract_user(self, claims: dict[str, Any]) -> User: ...


@runtime_checkable
class TokenValidator(Protocol):
    """Public-facing interface for token validation.

    Used by dependencies.py and the health endpoint.
    AuthService implements this Protocol.
    """

    async def validate_token(self, token: str) -> User: ...

    async def health_check(self) -> bool: ...


@runtime_checkable
class OAuthProvider(Protocol):
    """OAuth2 authorization code flow with PKCE.

    Covers the outbound auth flow:
    - Building the authorization redirect URL
    - Exchanging the authorization code for tokens
    - Refreshing tokens
    - Revoking tokens (logout)

    Implement once per OAuth2 provider (Keycloak, Auth0, etc.).
    """

    def build_authorization_url(
        self,
        redirect_uri: str,
        code_challenge: str,
        state: str | None = None,
        scope: str = "openid profile email",
    ) -> str: ...

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> TokenResponse: ...

    async def refresh_token(self, refresh_token: str) -> TokenResponse: ...

    async def logout(self, refresh_token: str) -> None: ...
