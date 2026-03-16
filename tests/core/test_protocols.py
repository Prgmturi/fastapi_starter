"""Tests for protocols — runtime_checkable verification.

Modules under test:
  src/fastapi_starter/core/protocols.py
  src/fastapi_starter/core/auth/protocols.py
Layer: Pure domain (structural typing verification)

WHY these tests exist: runtime_checkable protocols enable isinstance checks.
If @runtime_checkable is accidentally removed, isinstance() calls silently
return False. These tests detect that at test time.
"""

import pytest


class TestCoreProtocols:
    """Verify runtime_checkable decorators work for core protocols."""

    def test_health_checkable_is_runtime_checkable(self):
        """[CT] HealthCheckable supports isinstance()."""
        pytest.skip("Not implemented yet")

    def test_key_provider_is_runtime_checkable(self):
        """[CT] KeyProvider supports isinstance()."""
        pytest.skip("Not implemented yet")


class TestAuthProtocols:
    """Verify auth-specific protocols are runtime_checkable."""

    def test_token_decoder_is_runtime_checkable(self):
        """[CT] TokenDecoder supports isinstance()."""
        pytest.skip("Not implemented yet")

    def test_claim_extractor_is_runtime_checkable(self):
        """[CT] ClaimExtractor supports isinstance()."""
        pytest.skip("Not implemented yet")

    def test_token_validator_is_runtime_checkable(self):
        """[CT] TokenValidator supports isinstance()."""
        pytest.skip("Not implemented yet")

    def test_oauth_provider_is_runtime_checkable(self):
        """[CT] OAuthProvider supports isinstance()."""
        pytest.skip("Not implemented yet")
