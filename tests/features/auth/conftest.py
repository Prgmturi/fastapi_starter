"""Auth feature fixtures: mock OAuth provider, sample token responses."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi_starter.core.auth.dependencies import get_current_user
from fastapi_starter.core.auth.schemas import TokenResponse
from fastapi_starter.features.auth.router import get_oauth_provider


@pytest.fixture
def sample_token_response() -> TokenResponse:
    """Standard token response for testing."""
    return TokenResponse(
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        token_type="Bearer",
        expires_in=300,
    )


@pytest.fixture
def mock_oauth_provider(sample_token_response):
    """AsyncMock implementing OAuthProvider protocol."""
    mock = AsyncMock()
    mock.build_authorization_url = lambda **kwargs: "https://auth.example.com/auth?test=1"
    mock.exchange_code = AsyncMock(return_value=sample_token_response)
    mock.refresh_token = AsyncMock(return_value=sample_token_response)
    mock.logout = AsyncMock()
    return mock


@pytest.fixture
def app_with_oauth(app, mock_oauth_provider):
    """App with OAuthProvider dependency overridden."""
    app.dependency_overrides[get_oauth_provider] = lambda: mock_oauth_provider
    return app


@pytest.fixture
async def oauth_client(app_with_oauth) -> AsyncGenerator[AsyncClient]:
    """HTTP client with OAuth provider mocked."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_oauth),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest.fixture
async def authenticated_oauth_client(
    app_with_oauth, sample_user,
) -> AsyncGenerator[AsyncClient]:
    """HTTP client with both OAuth and auth mocked."""
    app_with_oauth.dependency_overrides[get_current_user] = lambda: sample_user
    async with AsyncClient(
        transport=ASGITransport(app=app_with_oauth),
        base_url="http://testserver",
    ) as ac:
        yield ac
