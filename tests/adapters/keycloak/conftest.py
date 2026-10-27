"""Keycloak adapter fixtures: the claims of a token, a mock key provider."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from fastapi_starter.core.auth.schemas import RoleEnum


@pytest.fixture
def sample_claims() -> dict[str, Any]:
    """Valid Keycloak JWT claims for a standard user."""
    return {
        "sub": "e37e9825-ac1c-4bd3-8380-579af43eac4823",
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
def sample_claims_minimal() -> dict[str, Any]:
    """Minimal valid claims — only required fields."""
    return {
        "sub": "minimal-user",
        "exp": 9999999999,
        "iat": 1700000000,
        "iss": "http://localhost:8080/realms/test-realm",
    }


@pytest.fixture
def mock_key_provider():
    """AsyncMock implementing KeyProvider protocol."""
    mock = AsyncMock()
    mock.get_signing_key_from_token = AsyncMock()
    mock.health_check = AsyncMock(return_value=True)
    return mock
