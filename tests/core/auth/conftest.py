"""Auth fixtures: mock ports (decoder, extractor, health checker) and an
AuthService built on them."""

from unittest.mock import AsyncMock, Mock

import pytest

from fastapi_starter.core.auth.service import AuthService


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
def auth_service(mock_token_decoder, mock_claim_extractor, mock_health_checker):
    """Real AuthService wired with mock dependencies.

    Use this to test the decode -> extract pipeline without I/O.
    """
    return AuthService(
        decoder=mock_token_decoder,
        extractor=mock_claim_extractor,
        health_checker=mock_health_checker,
    )
