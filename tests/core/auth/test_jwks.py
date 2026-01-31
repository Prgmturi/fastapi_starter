"""Tests for JWKSTokenDecoder — JWT decoding and verification.

Module under test: src/fastapi_starter/core/auth/jwks.py
Layer: Core logic (mock KeyProvider at protocol boundary)

WHY these tests exist: JWKSTokenDecoder wraps PyJWT and converts all library
exceptions into domain UnauthorizedError. This is the anti-corruption layer —
we must verify that no PyJWT exception leaks out.

NOTE: Happy-path tests require generating a real RSA key pair and signing
a JWT with it. The public key is provided via mock_key_provider.
"""

import time
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from fastapi_starter.core.auth.jwks import JWKSTokenDecoder
from fastapi_starter.core.auth.protocols import TokenDecoder
from fastapi_starter.core.exceptions import UnauthorizedError
from fastapi_starter.core.protocols import HealthCheckable

ISSUER = "http://localhost:8080/realms/test-realm"


@pytest.fixture
def rsa_private_key():
    """RSA private key for signing test JWTs."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def mock_jwk(rsa_private_key):
    """Mock JWK object with the public key, as returned by KeyProvider."""
    jwk = MagicMock()
    jwk.key = rsa_private_key.public_key()
    return jwk


@pytest.fixture
def jwks_decoder(mock_key_provider) -> JWKSTokenDecoder:
    """JWKSTokenDecoder wired with a mock KeyProvider."""
    return JWKSTokenDecoder(key_provider=mock_key_provider, issuer=ISSUER)


def _sign_token(
    private_key, claims: dict | None = None, headers: dict | None = None
) -> str:
    """Helper to sign a JWT with the given RSA key."""
    default_claims = {
        "sub": "user-1",
        "iss": ISSUER,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return pyjwt.encode(
        {**default_claims, **(claims or {})},
        private_key,
        algorithm="RS256",
        headers=headers or {"kid": "test-kid"},
    )


class TestDecode:
    """JWKSTokenDecoder.decode() — JWT verification via KeyProvider.

    WHY: This class is the anti-corruption layer between PyJWT and our
    domain. It must convert EVERY possible PyJWT exception into
    UnauthorizedError. If any exception leaks, the global exception
    handler returns 500 instead of 401.
    """

    async def test_valid_token_returns_claims(
        self,
        jwks_decoder,
        mock_key_provider,
        mock_jwk,
        rsa_private_key,
    ):
        """[HP] Valid JWT returns decoded claims dict."""
        mock_key_provider.get_signing_key_from_token.return_value = mock_jwk
        token = _sign_token(rsa_private_key)

        claims = await jwks_decoder.decode(token)

        assert claims["sub"] == "user-1"
        assert claims["iss"] == ISSUER

    async def test_expired_token_raises_unauthorized_with_message(
        self,
        jwks_decoder,
        mock_key_provider,
        mock_jwk,
        rsa_private_key,
    ):
        """[EC] ExpiredSignatureError -> UnauthorizedError('Token expired')."""
        mock_key_provider.get_signing_key_from_token.return_value = mock_jwk
        token = _sign_token(rsa_private_key, claims={"exp": int(time.time()) - 100})

        with pytest.raises(UnauthorizedError, match="Token expired"):
            await jwks_decoder.decode(token)

    async def test_invalid_signature_raises_unauthorized(
        self,
        jwks_decoder,
        mock_key_provider,
    ):
        """[EC] Invalid signature -> UnauthorizedError('Invalid token')."""
        # Sign with one key, verify with another
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = _sign_token(wrong_key)

        wrong_jwk = MagicMock()
        wrong_jwk.key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        ).public_key()
        mock_key_provider.get_signing_key_from_token.return_value = wrong_jwk

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(token)

    async def test_malformed_token_raises_unauthorized(
        self,
        jwks_decoder,
        mock_key_provider,
    ):
        """[EC] Garbage string -> UnauthorizedError('Invalid token')."""
        mock_key_provider.get_signing_key_from_token.side_effect = (
            pyjwt.exceptions.DecodeError("Not enough segments")
        )

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode("not-a-jwt")

    async def test_key_provider_value_error_raises_unauthorized(
        self,
        jwks_decoder,
        mock_key_provider,
    ):
        """[EC] KeyProvider raises ValueError (kid not found) -> UnauthorizedError.

        WHY: When Keycloak rotates keys and the kid is not found,
        KeyProvider raises ValueError. We must translate this cleanly.
        """
        mock_key_provider.get_signing_key_from_token.side_effect = ValueError(
            "Unable to find a signing key that matches: test-kid"
        )

        with pytest.raises(UnauthorizedError):
            await jwks_decoder.decode("some-token")

    async def test_key_provider_runtime_error_raises_unauthorized(
        self,
        jwks_decoder,
        mock_key_provider,
    ):
        """[EC] KeyProvider raises RuntimeError (fetch failed) -> UnauthorizedError."""
        mock_key_provider.get_signing_key_from_token.side_effect = RuntimeError(
            "JWKS endpoint unreachable"
        )

        with pytest.raises(UnauthorizedError, match="Authentication failed"):
            await jwks_decoder.decode("some-token")

    async def test_unexpected_exception_raises_unauthorized(
        self,
        jwks_decoder,
        mock_key_provider,
    ):
        """[EC] Any other exception -> UnauthorizedError('Authentication failed').

        WHY: Catch-all ensures no internal exception ever leaks to the caller.
        """
        mock_key_provider.get_signing_key_from_token.side_effect = OSError("disk error")

        with pytest.raises(UnauthorizedError, match="Authentication failed"):
            await jwks_decoder.decode("some-token")


class TestHealthCheck:
    """JWKSTokenDecoder.health_check() — delegates to KeyProvider.

    WHY: Ensures health checking goes through to the actual JWKS endpoint
    (via KeyProvider), not a cached/stale state.
    """

    async def test_delegates_to_key_provider(self, jwks_decoder, mock_key_provider):
        """[HP] Calls key_provider.health_check() and returns result."""
        mock_key_provider.health_check.return_value = True

        result = await jwks_decoder.health_check()

        assert result is True
        mock_key_provider.health_check.assert_called_once()

    async def test_key_provider_failure_propagates(
        self, jwks_decoder, mock_key_provider
    ):
        """[EC] Exception from key_provider propagates."""
        mock_key_provider.health_check.side_effect = RuntimeError("unreachable")

        with pytest.raises(RuntimeError, match="unreachable"):
            await jwks_decoder.health_check()


class TestTokenDecoderProtocol:
    """Contract test: JWKSTokenDecoder satisfies TokenDecoder.

    WHY: AuthService depends on TokenDecoder Protocol.
    """

    def test_implements_token_decoder_protocol(self):
        """[CT] isinstance(decoder, TokenDecoder) is True."""
        mock_provider = AsyncMock()
        decoder = JWKSTokenDecoder(key_provider=mock_provider, issuer="test")
        assert isinstance(decoder, TokenDecoder)

    def test_implements_health_checkable_protocol(self):
        """[CT] isinstance(decoder, HealthCheckable) is True."""
        mock_provider = AsyncMock()
        decoder = JWKSTokenDecoder(key_provider=mock_provider, issuer="test")
        assert isinstance(decoder, HealthCheckable)
