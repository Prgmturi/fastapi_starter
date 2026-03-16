"""Tests for AuthService — token validation orchestrator.

Module under test: src/fastapi_starter/core/auth/service.py
Layer: Core logic (mock decoder, extractor, health_checker at protocol boundary)

WHY these tests exist: AuthService is the orchestrator. It wires decoder +
extractor. We verify the decode-then-extract pipeline and that exceptions
propagate correctly. Every protected endpoint calls this.
"""

import pytest


class TestValidateToken:
    """AuthService.validate_token() — the decode -> extract pipeline.

    WHY: This is the critical authentication path. Every protected endpoint
    calls this. We must verify:
    1. Correct delegation to decoder then extractor (ordering matters)
    2. Decoder exceptions propagate unchanged (no swallowing)
    3. Extractor exceptions propagate unchanged
    """

    async def test_valid_token_returns_user(self):
        """[HP] Token decoded, claims extracted, User returned."""
        pytest.skip("Not implemented yet")

    async def test_decoder_called_with_token(self):
        """[HP] Decoder.decode receives the raw token string.

        WHY: Verifies the service passes the token as-is, without
        modification (e.g., no accidental stripping of 'Bearer ' prefix).
        """
        pytest.skip("Not implemented yet")

    async def test_extractor_called_with_decoded_claims(self):
        """[HP] Extractor receives the exact dict returned by decoder."""
        pytest.skip("Not implemented yet")

    async def test_decoder_failure_propagates_unauthorized(self):
        """[EC] UnauthorizedError from decoder propagates to caller."""
        pytest.skip("Not implemented yet")

    async def test_extractor_failure_propagates_unauthorized(self):
        """[EC] UnauthorizedError from extractor propagates to caller."""
        pytest.skip("Not implemented yet")


class TestHealthCheck:
    """AuthService.health_check() — delegates to health_checker.

    WHY: The health endpoint calls this. We verify pure delegation
    (no transformation, no swallowing of exceptions).
    """

    async def test_healthy_backend_returns_true(self):
        """[HP] Delegates to health_checker, returns True."""
        pytest.skip("Not implemented yet")

    async def test_unhealthy_backend_propagates_exception(self):
        """[EC] Exception from health_checker propagates."""
        pytest.skip("Not implemented yet")


class TestTokenValidatorProtocol:
    """Contract test: AuthService satisfies TokenValidator.

    WHY: FastAPI dependencies and health endpoints depend on
    TokenValidator Protocol. This locks the structural contract.
    """

    def test_implements_token_validator_protocol(self):
        """[CT] isinstance(auth_service, TokenValidator) is True."""
        pytest.skip("Not implemented yet")
