"""Tests for AuthService — token validation orchestrator.

Module under test: src/fastapi_starter/core/auth/service.py
Layer: Core logic (mock decoder, extractor, health_checker at protocol boundary)

WHY these tests exist: AuthService is the orchestrator. It wires decoder +
extractor. We verify the decode-then-extract pipeline and that exceptions
propagate correctly. Every protected endpoint calls this.
"""

import pytest

from fastapi_starter.core.auth.protocols import TokenValidator
from fastapi_starter.core.exceptions import UnauthorizedError


class TestValidateToken:
    """AuthService.validate_token() — the decode -> extract pipeline.

    WHY: This is the critical authentication path. Every protected endpoint
    calls this. We must verify:
    1. Correct delegation to decoder then extractor (ordering matters)
    2. Decoder exceptions propagate unchanged (no swallowing)
    3. Extractor exceptions propagate unchanged
    """

    async def test_valid_token_returns_user(
        self, auth_service, mock_token_decoder, mock_claim_extractor, sample_user,
    ):
        """[HP] Token decoded, claims extracted, User returned."""
        mock_token_decoder.decode.return_value = {"sub": "user-1"}
        mock_claim_extractor.extract_user.return_value = sample_user

        user = await auth_service.validate_token("valid-token")

        assert user == sample_user

    async def test_decoder_called_with_token(
        self, auth_service, mock_token_decoder,
    ):
        """[HP] Decoder.decode receives the raw token string.

        WHY: Verifies the service passes the token as-is, without
        modification (e.g., no accidental stripping of 'Bearer ' prefix).
        """
        await auth_service.validate_token("my-raw-token")

        mock_token_decoder.decode.assert_called_once_with("my-raw-token")

    async def test_extractor_called_with_decoded_claims(
        self, auth_service, mock_token_decoder, mock_claim_extractor,
    ):
        """[HP] Extractor receives the exact dict returned by decoder."""
        decoded_claims = {"sub": "user-1", "iss": "test-issuer"}
        mock_token_decoder.decode.return_value = decoded_claims

        await auth_service.validate_token("token")

        mock_claim_extractor.extract_user.assert_called_once_with(decoded_claims)

    async def test_decoder_failure_propagates_unauthorized(
        self, auth_service, mock_token_decoder,
    ):
        """[EC] UnauthorizedError from decoder propagates to caller."""
        mock_token_decoder.decode.side_effect = UnauthorizedError("token expired")

        with pytest.raises(UnauthorizedError, match="token expired"):
            await auth_service.validate_token("expired-token")

    async def test_extractor_failure_propagates_unauthorized(
        self, auth_service, mock_token_decoder, mock_claim_extractor,
    ):
        """[EC] UnauthorizedError from extractor propagates to caller."""
        mock_token_decoder.decode.return_value = {"sub": "user-1"}
        mock_claim_extractor.extract_user.side_effect = UnauthorizedError("bad claims")

        with pytest.raises(UnauthorizedError, match="bad claims"):
            await auth_service.validate_token("token")


class TestHealthCheck:
    """AuthService.health_check() — delegates to health_checker.

    WHY: The health endpoint calls this. We verify pure delegation
    (no transformation, no swallowing of exceptions).
    """

    async def test_healthy_backend_returns_true(
        self, auth_service, mock_health_checker,
    ):
        """[HP] Delegates to health_checker, returns True."""
        mock_health_checker.health_check.return_value = True

        result = await auth_service.health_check()

        assert result is True
        mock_health_checker.health_check.assert_called_once()

    async def test_unhealthy_backend_propagates_exception(
        self, auth_service, mock_health_checker,
    ):
        """[EC] Exception from health_checker propagates."""
        mock_health_checker.health_check.side_effect = RuntimeError("backend down")

        with pytest.raises(RuntimeError, match="backend down"):
            await auth_service.health_check()


class TestTokenValidatorProtocol:
    """Contract test: AuthService satisfies TokenValidator.

    WHY: FastAPI dependencies and health endpoints depend on
    TokenValidator Protocol. This locks the structural contract.
    """

    def test_implements_token_validator_protocol(self, auth_service):
        """[CT] isinstance(auth_service, TokenValidator) is True."""
        assert isinstance(auth_service, TokenValidator)
