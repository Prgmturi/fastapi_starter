"""
Root conftest — global fixtures available to all tests.

Fixture hierarchy:
    tests/conftest.py           ← YOU ARE HERE (app, client, settings, users)
    tests/core/auth/conftest.py ← auth-specific (claims, tokens, mock decoders)
    tests/core/database/conftest.py ← db-specific (mock session, mock manager)
    tests/features/conftest.py  ← feature-level (dependency overrides)
    tests/features/auth/conftest.py ← auth endpoints (mock oauth provider)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi_starter.core.auth.dependencies import get_auth_service, get_current_user
from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.core.database.dependencies import get_db_manager
from fastapi_starter.main import create_app

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _noop_lifespan(app):
    """Lifespan that skips all service initialization."""
    yield


@pytest.fixture
def app(mock_auth_service, mock_db_provider):
    """FastAPI app with external dependencies replaced by mocks."""
    application = create_app()

    # Skip the real lifespan (no DB, no Keycloak)
    application.router.lifespan_context = _noop_lifespan
    application.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    application.dependency_overrides[get_db_manager] = lambda: mock_db_provider
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient]:
    """Async HTTP client for endpoint testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest.fixture
def authenticated_app(app, sample_user):
    """App with get_current_user overridden to return sample_user."""
    app.dependency_overrides[get_current_user] = lambda: sample_user
    return app


@pytest.fixture
async def authenticated_client(
    authenticated_app,
) -> AsyncGenerator[AsyncClient]:
    """Client that bypasses authentication — returns sample_user."""
    async with AsyncClient(
        transport=ASGITransport(app=authenticated_app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Mock services
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_auth_service():
    """AsyncMock implementing TokenValidator protocol."""
    mock = AsyncMock()
    mock.validate_token = AsyncMock()
    mock.health_check = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_db_provider():
    """AsyncMock implementing DatabaseProvider / HealthCheckable."""
    mock = AsyncMock()
    mock.health_check = AsyncMock(return_value=True)
    return mock


# ---------------------------------------------------------------------------
# Sample domain objects
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_user() -> User:
    """Standard test user with USER role."""
    return User(
        id="e37e9825-ac1c-4bd3-8380-579af43eac4823",
        username="test_user",
        email="test@example.com",
        email_verified=True,
        first_name="Test",
        last_name="User",
        roles=[RoleEnum.USER],
    )


@pytest.fixture
def sample_admin_user() -> User:
    """Admin user with ADMIN + USER roles."""
    return User(
        id="admin-456",
        username="admin_user",
        email="admin@example.com",
        email_verified=True,
        first_name="Admin",
        last_name="User",
        roles=[RoleEnum.ADMIN, RoleEnum.USER],
    )


@pytest.fixture
def sample_superadmin_user() -> User:
    """Superadmin user with SUPERADMIN role."""
    return User(
        id="superadmin-789",
        username="superadmin",
        email="super@example.com",
        email_verified=True,
        first_name="Super",
        last_name="Admin",
        roles=[RoleEnum.SUPERADMIN],
    )
