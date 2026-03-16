"""Auth-specific fixtures: JWT claims, mock decoders, mock extractors."""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.core.auth.service import AuthService


@pytest.fixture
def sample_claims() -> dict[str, Any]:
    """Valid Keycloak JWT claims for a standard user."""
    return {
        "sub": "user-123",
        "exp": 9999999999,
        "iat": 1700000000,
        "iss": "http://localhost:8080/realms/test-realm",
        "preferred_username": "test_user",
        "email": "test@example.com",
        "email_verified": True,
        "given_name": "Test",
        "family_name": "User",
        "realm_access": {"roles": [RoleEnum.USER.value]},
        "resource_access": {
            "test-client": {"roles": [RoleEnum.USER.value]},
        },
    }


@pytest.fixture
def sample_admin_claims(sample_claims) -> dict[str, Any]:
    """JWT claims with admin role."""
    return {
        **sample_claims,
        "sub": "admin-456",
        "preferred_username": "admin_user",
        "realm_access": {
            "roles": [RoleEnum.ADMIN.value, RoleEnum.USER.value],
        },
    }


@pytest.fixture
def sample_claims_minimal() -> dict[str, Any]:
    """Minimal valid claims — only required fields."""
    return {
        "sub": "minimal-user",
        "exp": 9999999999,
        "iat": 1700000000,
        "iss": "http://localhost:8080/realms/test-realm",
    }


@pytest.fixture
def mock_token_decoder():
    """AsyncMock implementing TokenDecoder protocol."""
    mock = AsyncMock()
    mock.decode = AsyncMock(return_value={})
    return mock


@pytest.fixture
def mock_claim_extractor(sample_user):
    """Mock implementing ClaimExtractor protocol."""
    mock = Mock()
    mock.extract_user = Mock(return_value=sample_user)
    return mock


@pytest.fixture
def mock_health_checker():
    """AsyncMock implementing HealthCheckable protocol."""
    mock = AsyncMock()
    mock.health_check = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_key_provider():
    """AsyncMock implementing KeyProvider protocol."""
    mock = AsyncMock()
    mock.get_signing_key_from_token = AsyncMock()
    mock.health_check = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def auth_service(mock_token_decoder, mock_claim_extractor, mock_health_checker):
    """Real AuthService wired with mock dependencies.

    Use this to test the decode -> extract pipeline without I/O.
    """
    return AuthService(
        decoder=mock_token_decoder,
        extractor=mock_claim_extractor,
        health_checker=mock_health_checker,
    )
