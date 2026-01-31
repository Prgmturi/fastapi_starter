"""Tests for protocols — runtime_checkable verification.

Modules under test:
  src/fastapi_starter/core/protocols.py
  src/fastapi_starter/core/auth/protocols.py
Layer: Pure domain (structural typing verification)

WHY these tests exist: runtime_checkable protocols enable isinstance checks.
If @runtime_checkable is accidentally removed, isinstance() calls silently
return False. These tests detect that at test time.
"""

from fastapi_starter.core.auth.protocols import (
    ClaimExtractor,
    OAuthProvider,
    TokenDecoder,
    TokenValidator,
)
from fastapi_starter.core.protocols import HealthCheckable, KeyProvider


class TestCoreProtocols:
    """Verify runtime_checkable decorators work for core protocols."""

    def test_health_checkable_is_runtime_checkable(self):
        """[CT] HealthCheckable supports isinstance()."""

        class _Impl:
            async def health_check(self) -> bool:
                return True

        assert isinstance(_Impl(), HealthCheckable)

    def test_key_provider_is_runtime_checkable(self):
        """[CT] KeyProvider supports isinstance()."""

        class _Impl:
            async def get_signing_key_from_token(self, token):
                return None

            async def health_check(self) -> bool:
                return True

        assert isinstance(_Impl(), KeyProvider)


class TestAuthProtocols:
    """Verify auth-specific protocols are runtime_checkable."""

    def test_token_decoder_is_runtime_checkable(self):
        """[CT] TokenDecoder supports isinstance()."""

        class _Impl:
            async def decode(self, token):
                return {}

        assert isinstance(_Impl(), TokenDecoder)

    def test_claim_extractor_is_runtime_checkable(self):
        """[CT] ClaimExtractor supports isinstance()."""

        class _Impl:
            def extract_user(self, claims):
                return None

        assert isinstance(_Impl(), ClaimExtractor)

    def test_token_validator_is_runtime_checkable(self):
        """[CT] TokenValidator supports isinstance()."""

        class _Impl:
            async def validate_token(self, token):
                return None

            async def health_check(self) -> bool:
                return True

        assert isinstance(_Impl(), TokenValidator)

    def test_oauth_provider_is_runtime_checkable(self):
        """[CT] OAuthProvider supports isinstance()."""

        class _Impl:
            def build_authorization_url(
                self,
                redirect_uri,
                code_challenge,
                state=None,
                scope="openid",
            ):
                return ""

            async def exchange_code(self, code, code_verifier, redirect_uri):
                return None

            async def refresh_token(self, refresh_token):
                return None

            async def logout(self, refresh_token):
                return None

        assert isinstance(_Impl(), OAuthProvider)
