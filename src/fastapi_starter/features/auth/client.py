
from urllib.parse import urlencode
import httpx

from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.exceptions import ExternalServiceError, UnauthorizedError
from fastapi_starter.core.logging import get_logger
from fastapi_starter.features.auth.schemas import TokenResponse

logger = get_logger(__name__)


class KeycloakClient:
    """
    Client for Keycloak token operations.

    Handles:
    - Authorization code exchange (with PKCE)
    - Token refresh (with rotation)
    - Token revocation (logout)
    """

    def __init__(self, settings: KeycloakSettings) -> None:
        self._settings = settings

    @property
    def token_url(self) -> str:
        """Keycloak token endpoint."""
        return self._settings.token_url

    @property
    def logout_url(self) -> str:
        """Keycloak logout endpoint."""
        return (
            f"{self._settings.server_url}/realms/"
            f"{self._settings.realm}/protocol/openid-connect/logout"
        )

    @property
    def auth_url(self) -> str:
        """Keycloak authorization endpoint."""
        return self._settings.auth_url

    def build_authorization_url(
        self,
        redirect_uri: str,
        code_challenge: str,
        state: str | None = None,
        scope: str = "openid profile email",
    ) -> str:
        """
        Build authorization URL for OAuth flow.

        Args:
            redirect_uri: Where Keycloak redirects after login
            code_challenge: PKCE code challenge (SHA256 hash of verifier)
            state: Optional state parameter for CSRF protection
            scope: OAuth scopes to request

        Returns:
            Full authorization URL
        """
        params = {
            "client_id": self._settings.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": scope,
        }

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> TokenResponse:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from Keycloak callback
            code_verifier: PKCE code verifier (original, not hashed)
            redirect_uri: Must match the one used in authorization request

        Returns:
            Token response with access and refresh tokens

        Raises:
            UnauthorizedError: If code is invalid or expired
            ExternalServiceError: If Keycloak is unreachable
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
        }

        return await self._token_request(data, "code_exchange")

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """
        Refresh access token using refresh token.

        With rotation enabled, returns new refresh token too.

        Args:
            refresh_token: Current refresh token

        Returns:
            New tokens (access + refresh with rotation)

        Raises:
            UnauthorizedError: If refresh token is invalid or expired
            ExternalServiceError: If Keycloak is unreachable
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
            "refresh_token": refresh_token,
        }

        return await self._token_request(data, "token_refresh")

    async def logout(self, refresh_token: str) -> None:
        """
        Revoke refresh token (logout).

        Args:
            refresh_token: Refresh token to revoke

        Raises:
            ExternalServiceError: If Keycloak is unreachable
        """
        data = {
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
            "refresh_token": refresh_token,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.logout_url,
                    data=data,
                    timeout=self._settings.request_timeout,
                )

                # 204 = success, 400 = token already invalid (ok)
                if response.status_code not in (200, 204, 400):
                    logger.warning(
                        "logout_failed",
                        status_code=response.status_code,
                        response=response.text,
                    )

                logger.info("user_logged_out")

        except httpx.HTTPError as e:
            logger.error("logout_request_failed", error=str(e))
            raise ExternalServiceError("Keycloak", str(e)) from None

    async def _token_request(
        self,
        data: dict,
        operation: str,
    ) -> TokenResponse:
        """
        Make token request to Keycloak.

        Args:
            data: Form data for token request
            operation: Operation name for logging

        Returns:
            Token response

        Raises:
            UnauthorizedError: If request fails with 400/401
            ExternalServiceError: If Keycloak is unreachable
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data=data,
                    timeout=self._settings.request_timeout,
                )

                if response.status_code == 400:
                    error_data = response.json()
                    error_desc = error_data.get("error_description", "Invalid request")
                    logger.warning(
                        f"{operation}_failed",
                        error=error_data.get("error"),
                        description=error_desc,
                    )
                    raise UnauthorizedError(error_desc) from None

                if response.status_code == 401:
                    logger.warning(f"{operation}_unauthorized")
                    raise UnauthorizedError("Invalid credentials") from None

                response.raise_for_status()

                token_data = response.json()
                logger.debug(f"{operation}_success")

                return TokenResponse(
                    access_token=token_data["access_token"],
                    refresh_token=token_data["refresh_token"],
                    token_type=token_data.get("token_type", "Bearer"),
                    expires_in=token_data.get("expires_in", 300),
                )

        except httpx.HTTPError as e:
            logger.error(f"{operation}_request_failed", error=str(e))
            raise ExternalServiceError("Keycloak", str(e)) from None