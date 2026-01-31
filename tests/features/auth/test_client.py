"""Tests for KeycloakClient — HTTP token operations.

Module under test: src/fastapi_starter/features/auth/client.py
Layer: Infrastructure adapter (mock httpx responses)

WHY these tests exist: KeycloakClient makes HTTP calls to Keycloak.
We must verify it correctly handles all Keycloak response scenarios
and maps them to domain exceptions.
"""

from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from fastapi_starter.core.auth.protocols import OAuthProvider
from fastapi_starter.core.auth.schemas import TokenResponse
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.exceptions import ExternalServiceError, UnauthorizedError
from fastapi_starter.features.auth.client import KeycloakClient


@pytest.fixture
def keycloak_settings() -> KeycloakSettings:
    return KeycloakSettings(
        scheme="http",
        host="localhost",
        port=8080,
        realm="test-realm",
        client_id="test-client",
        client_secret="test-secret",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def mock_http_client() -> AsyncMock:
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def keycloak_client(keycloak_settings, mock_http_client) -> KeycloakClient:
    client = KeycloakClient(keycloak_settings)
    client._client = mock_http_client
    return client


def _mock_response(
    status_code: int, json_data: dict | None = None, text: str = ""
) -> MagicMock:
    """Create a mock httpx Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text
    if json_data is not None:
        response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error",
            request=MagicMock(),
            response=response,
        )
    return response


class TestBuildAuthorizationUrl:
    """KeycloakClient.build_authorization_url() — URL construction.

    WHY: Pure function (no I/O). We verify URL parameters match the
    OAuth2 + PKCE spec. Wrong params = user cannot log in.
    """

    def test_includes_required_params(self, keycloak_client):
        """[HP] URL includes client_id, response_type, redirect_uri,
        code_challenge, code_challenge_method, scope."""
        url = keycloak_client.build_authorization_url(
            redirect_uri="http://localhost:3000/callback",
            code_challenge="abc123",
        )
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert params["client_id"] == ["test-client"]
        assert params["response_type"] == ["code"]
        assert params["redirect_uri"] == ["http://localhost:3000/callback"]
        assert params["code_challenge"] == ["abc123"]
        assert "scope" in params

    def test_includes_state_when_provided(self, keycloak_client):
        """[HP] state param included in URL when not None."""
        url = keycloak_client.build_authorization_url(
            redirect_uri="http://localhost:3000/callback",
            code_challenge="abc123",
            state="my-state",
        )
        params = parse_qs(urlparse(url).query)

        assert params["state"] == ["my-state"]

    def test_omits_state_when_not_provided(self, keycloak_client):
        """[EC] state param NOT in URL when None."""
        url = keycloak_client.build_authorization_url(
            redirect_uri="http://localhost:3000/callback",
            code_challenge="abc123",
            state=None,
        )
        params = parse_qs(urlparse(url).query)

        assert "state" not in params

    def test_uses_s256_challenge_method(self, keycloak_client):
        """[HP] code_challenge_method is always S256 (PKCE spec)."""
        url = keycloak_client.build_authorization_url(
            redirect_uri="http://localhost:3000/callback",
            code_challenge="abc123",
        )
        params = parse_qs(urlparse(url).query)

        assert params["code_challenge_method"] == ["S256"]

    def test_default_scope_is_openid_profile_email(self, keycloak_client):
        """[HP] Default scope = 'openid profile email'."""
        url = keycloak_client.build_authorization_url(
            redirect_uri="http://localhost:3000/callback",
            code_challenge="abc123",
        )
        params = parse_qs(urlparse(url).query)

        assert params["scope"] == ["openid profile email"]


class TestExchangeCode:
    """KeycloakClient.exchange_code() — authorization code exchange.

    WHY: Maps Keycloak HTTP responses to domain types/exceptions.
    We mock httpx to simulate all possible Keycloak responses.
    """

    async def test_successful_exchange_returns_token_response(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[HP] Keycloak returns 200 -> TokenResponse."""
        mock_http_client.post.return_value = _mock_response(
            200,
            {
                "access_token": "at-123",
                "refresh_token": "rt-456",
                "token_type": "Bearer",
                "expires_in": 300,
            },
        )

        result = await keycloak_client.exchange_code(
            code="auth-code",
            code_verifier="verifier",
            redirect_uri="http://test",
        )

        assert isinstance(result, TokenResponse)
        assert result.access_token == "at-123"
        assert result.refresh_token == "rt-456"

    async def test_invalid_code_400_raises_unauthorized(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[EC] Keycloak returns 400 -> UnauthorizedError with description."""
        mock_http_client.post.return_value = _mock_response(
            400,
            {
                "error": "invalid_grant",
                "error_description": "Code not valid",
            },
        )

        with pytest.raises(UnauthorizedError, match="Code not valid"):
            await keycloak_client.exchange_code(
                code="bad-code",
                code_verifier="v",
                redirect_uri="http://test",
            )

    async def test_invalid_credentials_401_raises_unauthorized(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[EC] Keycloak returns 401 -> UnauthorizedError('Invalid credentials')."""
        mock_http_client.post.return_value = _mock_response(401, {})

        with pytest.raises(UnauthorizedError, match="Invalid credentials"):
            await keycloak_client.exchange_code(
                code="code",
                code_verifier="v",
                redirect_uri="http://test",
            )

    async def test_keycloak_unreachable_raises_external_service_error(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[EC] httpx.HTTPError -> ExternalServiceError('Keycloak')."""
        mock_http_client.post.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(ExternalServiceError):
            await keycloak_client.exchange_code(
                code="code",
                code_verifier="v",
                redirect_uri="http://test",
            )

    async def test_unexpected_error_raises_external_service_error(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[EC] Any other exception -> ExternalServiceError."""
        mock_http_client.post.side_effect = RuntimeError("unexpected")

        with pytest.raises(ExternalServiceError):
            await keycloak_client.exchange_code(
                code="code",
                code_verifier="v",
                redirect_uri="http://test",
            )


class TestRefreshToken:
    """KeycloakClient.refresh_token() — token renewal.

    WHY: Same HTTP handling patterns as exchange_code, but with
    refresh_token grant_type.
    """

    async def test_successful_refresh_returns_new_tokens(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[HP] Keycloak returns 200 -> TokenResponse."""
        mock_http_client.post.return_value = _mock_response(
            200,
            {
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "token_type": "Bearer",
                "expires_in": 300,
            },
        )

        result = await keycloak_client.refresh_token("old-rt")

        assert isinstance(result, TokenResponse)
        assert result.access_token == "new-at"

    async def test_expired_refresh_raises_unauthorized(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[EC] Keycloak returns 400 (expired) -> UnauthorizedError."""
        mock_http_client.post.return_value = _mock_response(
            400,
            {
                "error": "invalid_grant",
                "error_description": "Token is not active",
            },
        )

        with pytest.raises(UnauthorizedError, match="Token is not active"):
            await keycloak_client.refresh_token("expired-rt")

    async def test_keycloak_unreachable_raises_external_service_error(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[EC] httpx.HTTPError -> ExternalServiceError."""
        mock_http_client.post.side_effect = httpx.ConnectError("timeout")

        with pytest.raises(ExternalServiceError):
            await keycloak_client.refresh_token("rt")


class TestLogout:
    """KeycloakClient.logout() — token revocation.

    WHY: Logout has special handling: 204=success, 400=already revoked (ok).
    Non-standard status codes are logged but not raised.
    """

    async def test_successful_logout_204(self, keycloak_client, mock_http_client):
        """[HP] Keycloak returns 204 -> no exception."""
        mock_http_client.post.return_value = _mock_response(204)

        await keycloak_client.logout("rt")  # Should not raise

    async def test_already_revoked_400_no_error(
        self, keycloak_client, mock_http_client
    ):
        """[EC] Keycloak returns 400 -> treated as success (token already invalid)."""
        mock_http_client.post.return_value = _mock_response(400)

        await keycloak_client.logout("already-revoked-rt")  # Should not raise

    async def test_unexpected_status_logged_no_error(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[EC] Keycloak returns 500 -> logged, no exception raised.

        WHY: Logout is best-effort. We do not want to show an error
        to the user if Keycloak has trouble during logout.
        """
        mock_http_client.post.return_value = _mock_response(500, text="Internal Error")

        await keycloak_client.logout("rt")  # Should not raise

    async def test_keycloak_unreachable_raises_external_service_error(
        self,
        keycloak_client,
        mock_http_client,
    ):
        """[EC] httpx.HTTPError -> ExternalServiceError.

        WHY: Unlike status code errors, network errors DO raise,
        because the client needs to know the request did not reach Keycloak.
        """
        mock_http_client.post.side_effect = httpx.ConnectError("refused")

        with pytest.raises(ExternalServiceError):
            await keycloak_client.logout("rt")


class TestOAuthProviderProtocol:
    """Contract test: KeycloakClient satisfies OAuthProvider.

    WHY: The auth router depends on OAuthProvider Protocol.
    """

    def test_implements_oauth_provider_protocol(self, keycloak_client):
        """[CT] KeycloakClient structurally satisfies OAuthProvider."""
        assert isinstance(keycloak_client, OAuthProvider)
