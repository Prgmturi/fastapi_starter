"""Tests for KeycloakClient — HTTP token operations.

Module under test: src/fastapi_starter/adapters/keycloak/client.py
Layer: Infrastructure adapter (mock httpx responses)

WHY these tests exist: KeycloakClient makes HTTP calls to Keycloak.
We must verify it correctly handles all Keycloak response scenarios
and maps them to domain exceptions.
"""

from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from fastapi_starter.adapters.keycloak.client import KeycloakClient
from fastapi_starter.core.auth.protocols import OAuthProvider
from fastapi_starter.core.auth.schemas import TokenResponse
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.exceptions import ExternalServiceError, UnauthorizedError


@pytest.fixture
def keycloak_settings() -> KeycloakSettings:
    return KeycloakSettings(
        scheme="http",
        host="localhost",
        port=8080,
        realm="test-realm",
        client_id="test-client",
        client_secret="test-secret",
    )


@pytest.fixture
def mock_http_client() -> AsyncMock:
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def keycloak_client(keycloak_settings, mock_http_client) -> KeycloakClient:
    return KeycloakClient(keycloak_settings, mock_http_client)


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


class TestLogout:
    """KeycloakClient.logout() — token revocation.

    WHY: 204 is a success, and so is 400: the token was already invalid.
    Any other answer, like a network error, raises ExternalServiceError
    (TestErrorContract); the router logs it and clears the cookie anyway.
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


# The OAuthProvider calls that reach Keycloak, by name.
KEYCLOAK_CALLS = {
    "exchange_code": lambda client: client.exchange_code(
        code="code", code_verifier="verifier", redirect_uri="http://test"
    ),
    "refresh_token": lambda client: client.refresh_token("rt"),
    "logout": lambda client: client.logout("rt"),
}
TOKEN_CALLS = {name: call for name, call in KEYCLOAK_CALLS.items() if name != "logout"}


# What the network can answer instead of Keycloak's normal reply.
def unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("All connection attempts failed", request=request)


def times_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


def server_error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, text="Internal Server Error")


def web_page(request: httpx.Request) -> httpx.Response:
    """A proxy, or a wrong URL, can answer 200 with a web page."""
    return httpx.Response(200, html="<html>Sign in</html>")


def json_without_tokens(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"token_type": "Bearer"})


class TestErrorContract:
    """The errors the OAuthProvider port promises, when Keycloak fails.

    WHY: callers catch only the two exceptions the port names:
    UnauthorizedError when Keycloak rejects the code or the refresh token,
    ExternalServiceError when it cannot answer properly. The logout route
    relies on them to clear the cookie whatever happens. Before, logout
    returned as if the token had been revoked when Keycloak answered 500,
    and the 502 of /auth/token showed the client httpx's own text, with
    Keycloak's internal URL.

    The network is an httpx.MockTransport: real requests and responses,
    so raise_for_status() and json() behave as in production.
    """

    @pytest.mark.parametrize("call", KEYCLOAK_CALLS.values(), ids=list(KEYCLOAK_CALLS))
    @pytest.mark.parametrize("network", [unreachable, times_out, server_error])
    async def test_keycloak_failure_raises_external_service_error(
        self, keycloak_settings, call, network
    ):
        """[EC] Network error or 5xx -> ExternalServiceError, nothing else."""
        async with httpx.AsyncClient(transport=httpx.MockTransport(network)) as http:
            with pytest.raises(ExternalServiceError) as exc_info:
                await call(KeycloakClient(keycloak_settings, http))

        # The message is the detail the client reads: no library text, no URL
        assert exc_info.value.message == "Error communicating with Keycloak"

    @pytest.mark.parametrize("call", TOKEN_CALLS.values(), ids=list(TOKEN_CALLS))
    @pytest.mark.parametrize("network", [web_page, json_without_tokens])
    async def test_answer_without_tokens_raises_external_service_error(
        self, keycloak_settings, call, network
    ):
        """[EC] 200 whose body is not a token set -> ExternalServiceError."""
        async with httpx.AsyncClient(transport=httpx.MockTransport(network)) as http:
            with pytest.raises(ExternalServiceError) as exc_info:
                await call(KeycloakClient(keycloak_settings, http))

        assert exc_info.value.message == "Error communicating with Keycloak"


class TestClientSecretSent:
    """The client secret in the form posted to Keycloak.

    WHY: the secret is a SecretStr, whose str() is "**********". Handed to
    httpx as it is, Keycloak would receive the stars and refuse every call,
    while the tests that mock the response stayed green.
    """

    @pytest.mark.parametrize("call", KEYCLOAK_CALLS.values(), ids=list(KEYCLOAK_CALLS))
    async def test_form_carries_the_configured_secret(self, keycloak_settings, call):
        """[HP] Every call posts client_secret with its real value."""
        forms = []

        def keycloak(request: httpx.Request) -> httpx.Response:
            forms.append(parse_qs(request.content.decode()))
            return httpx.Response(
                200,
                json={
                    "access_token": "at",
                    "refresh_token": "rt",
                    "token_type": "Bearer",
                    "expires_in": 300,
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(keycloak)) as http:
            await call(KeycloakClient(keycloak_settings, http))

        assert forms[0]["client_secret"] == ["test-secret"]


# The URL of KeycloakSettings each call posts to
CALL_URLS = {
    "exchange_code": "token_url",
    "refresh_token": "token_url",
    "logout": "logout_url",
}


class TestKeycloakUrls:
    """Where each call to Keycloak goes.

    WHY: the router logs a failed logout and answers 200 anyway. With a
    wrong logout URL every test passed, the end-to-end one too, and
    Keycloak never ended the session. Every URL comes from KeycloakSettings,
    which tests their form, the logout one included.
    """

    @pytest.mark.parametrize("name", list(KEYCLOAK_CALLS))
    async def test_call_posts_to_its_settings_url(self, keycloak_settings, name):
        """[HP] Each call posts to the URL KeycloakSettings gives for it."""
        urls = []

        def keycloak(request: httpx.Request) -> httpx.Response:
            urls.append(str(request.url))
            return httpx.Response(
                200,
                json={
                    "access_token": "at",
                    "refresh_token": "rt",
                    "token_type": "Bearer",
                    "expires_in": 300,
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(keycloak)) as http:
            await KEYCLOAK_CALLS[name](KeycloakClient(keycloak_settings, http))

        assert urls == [getattr(keycloak_settings, CALL_URLS[name])]


class TestOAuthProviderProtocol:
    """Contract test: KeycloakClient satisfies OAuthProvider.

    WHY: The auth router depends on OAuthProvider Protocol.
    """

    def test_implements_oauth_provider_protocol(self, keycloak_client):
        """[CT] KeycloakClient structurally satisfies OAuthProvider."""
        assert isinstance(keycloak_client, OAuthProvider)
