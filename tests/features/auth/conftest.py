"""Auth feature fixtures: mock OAuth provider, sample token responses."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi_starter.core.auth.dependencies import get_current_user
from fastapi_starter.core.auth.schemas import TokenResponse
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.features.auth.router import (
    get_keycloak_settings,
    get_oauth_provider,
)

# Cookie name used by all auth test fixtures — must match test_keycloak_settings.
TEST_COOKIE_NAME = "rt"


@pytest.fixture
def test_keycloak_settings() -> KeycloakSettings:
    """Deterministic KeycloakSettings for tests.

    Overrides get_keycloak_settings so tests are independent of the local .env.
    cookie_name='rt' (no __Host- prefix) because cookie_secure=False.
    """
    return KeycloakSettings(
        cookie_name=TEST_COOKIE_NAME,
        cookie_secure=False,
        cookie_samesite="lax",
        cookie_path="/",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def sample_token_response() -> TokenResponse:
    """Standard token response for testing."""
    return TokenResponse(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        token_type="Bearer",
        expires_in=300,
        refresh_expires_in=1800,
    )


@pytest.fixture
def mock_oauth_provider(sample_token_response):
    """AsyncMock implementing OAuthProvider protocol."""
    mock = AsyncMock()
    mock.build_authorization_url = lambda **kwargs: (
        "https://auth.example.com/auth?test=1"
    )
    mock.exchange_code = AsyncMock(return_value=sample_token_response)
    mock.refresh_token = AsyncMock(return_value=sample_token_response)
    mock.logout = AsyncMock()
    return mock


@pytest.fixture
def app_with_oauth(app, mock_oauth_provider, test_keycloak_settings):
    """App with OAuthProvider and KeycloakSettings dependencies overridden."""
    app.dependency_overrides[get_oauth_provider] = lambda: mock_oauth_provider
    app.dependency_overrides[get_keycloak_settings] = lambda: test_keycloak_settings
    return app


@pytest.fixture
async def oauth_client(app_with_oauth) -> AsyncGenerator[AsyncClient]:
    """HTTP client with OAuth provider mocked, no cookie set."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_oauth),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest.fixture
async def oauth_client_with_cookie(app_with_oauth) -> AsyncGenerator[AsyncClient]:
    """HTTP client with OAuth provider mocked and a valid refresh cookie set."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_oauth),
        base_url="http://testserver",
        cookies={TEST_COOKIE_NAME: "valid-rt"},
    ) as ac:
        yield ac


@pytest.fixture
async def authenticated_oauth_client(
    app_with_oauth,
    sample_user,
) -> AsyncGenerator[AsyncClient]:
    """HTTP client with both OAuth and auth mocked."""
    app_with_oauth.dependency_overrides[get_current_user] = lambda: sample_user
    async with AsyncClient(
        transport=ASGITransport(app=app_with_oauth),
        base_url="http://testserver",
    ) as ac:
        yield ac
