"""Tests for JWKSTokenDecoder — JWT decoding and verification.

Module under test: src/fastapi_starter/core/auth/jwks.py
Layer: Core logic (mock KeyProvider at protocol boundary)

WHY these tests exist: JWKSTokenDecoder wraps PyJWT and converts all library
exceptions into domain UnauthorizedError. This is the anti-corruption layer —
we must verify that no PyJWT exception leaks out.

NOTE: Happy-path tests require generating a real RSA key pair and signing
a JWT with it. The public key is provided via mock_key_provider.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode

from fastapi_starter.core.auth.jwks import JWKSTokenDecoder
from fastapi_starter.core.auth.protocols import TokenDecoder
from fastapi_starter.core.exceptions import UnauthorizedError
from fastapi_starter.core.protocols import HealthCheckable

ISSUER = "http://localhost:8080/realms/test-realm"
CLIENT_ID = "test-client"


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
def realm_key(mock_key_provider, mock_jwk):
    """The KeyProvider hands out the public half of rsa_private_key."""
    mock_key_provider.get_signing_key_from_token.return_value = mock_jwk


@pytest.fixture
def jwks_decoder(mock_key_provider) -> JWKSTokenDecoder:
    """JWKSTokenDecoder wired with a mock KeyProvider, accepting CLIENT_ID."""
    return JWKSTokenDecoder(
        key_provider=mock_key_provider, issuer=ISSUER, allowed_clients=[CLIENT_ID]
    )


def _access_token_claims(
    claims: dict | None = None, without: tuple[str, ...] = ()
) -> dict:
    """Claims of a valid Keycloak access token issued to CLIENT_ID.

    ``claims`` adds or overrides claims, ``without`` removes them.
    """
    now = int(time.time())
    payload = {
        "sub": "user-1",
        "iss": ISSUER,
        "exp": now + 3600,
        "iat": now,
        "typ": "Bearer",
        "azp": CLIENT_ID,
        **(claims or {}),
    }
    for name in without:
        del payload[name]
    return payload


def _sign_token(
    private_key,
    claims: dict | None = None,
    headers: dict | None = None,
    without: tuple[str, ...] = (),
) -> str:
    """Helper to sign a Keycloak-like access token with the given RSA key."""
    return pyjwt.encode(
        _access_token_claims(claims, without),
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

    async def test_key_provider_value_error_raises_generic_unauthorized(
        self,
        jwks_decoder,
        mock_key_provider,
    ):
        """[EC] KeyProvider raises ValueError (kid not found) -> 'Invalid token'.

        WHY: When Keycloak rotates keys and the kid is not found,
        KeyProvider raises ValueError. We must translate this cleanly and
        without its text: the kid comes from the caller, and the reason
        belongs in the log, not in the response.
        """
        mock_key_provider.get_signing_key_from_token.side_effect = ValueError(
            "Key attacker-chosen-kid not found in JWKS"
        )

        with pytest.raises(UnauthorizedError, match="^Invalid token$"):
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


@pytest.mark.usefixtures("realm_key")
class TestTokenUse:
    """typ and azp — only access tokens issued to the allowed clients.

    WHY: Keycloak signs ID tokens, refresh tokens and the tokens of every
    client in the realm with the same keys. A valid signature says "this
    comes from our realm", not "this token is meant for this API".
    """

    @pytest.mark.parametrize("token_type", ["ID", "Refresh", "Offline"])
    async def test_other_token_types_rejected(
        self, jwks_decoder, rsa_private_key, token_type
    ):
        """[EC] ID, refresh and offline tokens -> 401: only access tokens pass."""
        token = _sign_token(rsa_private_key, claims={"typ": token_type})

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(token)

    async def test_missing_type_rejected(self, jwks_decoder, rsa_private_key):
        """[EC] No typ claim -> 401: what the token is for is unknown."""
        token = _sign_token(rsa_private_key, without=("typ",))

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(token)

    async def test_token_for_another_client_rejected(
        self, jwks_decoder, rsa_private_key
    ):
        """[EC] azp of another client in the same realm -> 401."""
        token = _sign_token(rsa_private_key, claims={"azp": "billing-app"})

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(token)

    async def test_missing_authorized_party_rejected(
        self, jwks_decoder, rsa_private_key
    ):
        """[EC] No azp claim -> 401: the client is unknown."""
        token = _sign_token(rsa_private_key, without=("azp",))

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(token)

    async def test_every_allowed_client_accepted(
        self, mock_key_provider, rsa_private_key
    ):
        """[HP] A token from any client in allowed_clients passes."""
        decoder = JWKSTokenDecoder(
            key_provider=mock_key_provider,
            issuer=ISSUER,
            allowed_clients=[CLIENT_ID, "web-frontend"],
        )
        token = _sign_token(rsa_private_key, claims={"azp": "web-frontend"})

        claims = await decoder.decode(token)

        assert claims["azp"] == "web-frontend"


@pytest.mark.usefixtures("realm_key")
class TestStandardClaims:
    """iss, exp, iat, sub, aud and alg — what a signed token still needs.

    WHY: PyJWT checks these only as far as its options say. A missing
    option is a token accepted when it should be rejected.
    """

    @pytest.fixture
    def audience_decoder(self, mock_key_provider) -> JWKSTokenDecoder:
        """Decoder that also requires 'test-api' in the aud claim."""
        return JWKSTokenDecoder(
            key_provider=mock_key_provider,
            issuer=ISSUER,
            allowed_clients=[CLIENT_ID],
            audience="test-api",
        )

    async def test_wrong_issuer_rejected(self, jwks_decoder, rsa_private_key):
        """[EC] Token from another realm -> 401."""
        token = _sign_token(
            rsa_private_key, claims={"iss": "http://localhost:8080/realms/other"}
        )

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(token)

    async def test_expired_beyond_leeway_rejected(self, jwks_decoder, rsa_private_key):
        """[EC] Expired 31 s ago, past the 30 s leeway -> 'Token expired'."""
        token = _sign_token(rsa_private_key, claims={"exp": int(time.time()) - 31})

        with pytest.raises(UnauthorizedError, match="Token expired"):
            await jwks_decoder.decode(token)

    async def test_expired_within_leeway_accepted(self, jwks_decoder, rsa_private_key):
        """[HP] Expired 10 s ago -> still valid.

        WHY: the clocks of Keycloak and of this server never match exactly.
        Without a margin, a fresh token is refused whenever this server's
        clock runs a little ahead.
        """
        token = _sign_token(rsa_private_key, claims={"exp": int(time.time()) - 10})

        claims = await jwks_decoder.decode(token)

        assert claims["sub"] == "user-1"

    @pytest.mark.parametrize("claim", ["exp", "iat", "iss", "sub"])
    async def test_missing_required_claim_rejected(
        self, jwks_decoder, rsa_private_key, claim
    ):
        """[EC] Signed token without exp, iat, iss or sub -> 401."""
        token = _sign_token(rsa_private_key, without=(claim,))

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(token)

    async def test_unsigned_token_rejected(self, jwks_decoder):
        """[EC] alg "none", no signature at all -> 401."""
        token = pyjwt.encode(
            _access_token_claims(), None, algorithm="none", headers={"kid": "test-kid"}
        )

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(token)

    async def test_claims_changed_after_signing_rejected(
        self, jwks_decoder, rsa_private_key
    ):
        """[EC] Payload swapped after signing (another sub) -> 401."""
        header, _, signature = _sign_token(rsa_private_key).split(".")
        forged = base64url_encode(
            json.dumps(_access_token_claims({"sub": "admin-1"})).encode()
        ).decode()

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await jwks_decoder.decode(f"{header}.{forged}.{signature}")

    async def test_audience_not_checked_by_default(self, jwks_decoder, rsa_private_key):
        """[HP] No audience configured -> any aud passes.

        WHY: Keycloak puts 'account' in aud by default. Checking aud
        needs an audience mapper on the client first (decision 5).
        """
        token = _sign_token(rsa_private_key, claims={"aud": "account"})

        claims = await jwks_decoder.decode(token)

        assert claims["aud"] == "account"

    async def test_expected_audience_accepted(self, audience_decoder, rsa_private_key):
        """[HP] audience configured and present in aud -> valid."""
        token = _sign_token(rsa_private_key, claims={"aud": ["account", "test-api"]})

        claims = await audience_decoder.decode(token)

        assert "test-api" in claims["aud"]

    async def test_other_audience_rejected(self, audience_decoder, rsa_private_key):
        """[EC] audience configured, token meant for another audience -> 401."""
        token = _sign_token(rsa_private_key, claims={"aud": "account"})

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await audience_decoder.decode(token)

    async def test_missing_audience_rejected(self, audience_decoder, rsa_private_key):
        """[EC] audience configured, token without aud -> 401."""
        token = _sign_token(rsa_private_key)

        with pytest.raises(UnauthorizedError, match="Invalid token"):
            await audience_decoder.decode(token)


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
        decoder = JWKSTokenDecoder(
            key_provider=mock_provider, issuer="test", allowed_clients=["test"]
        )
        assert isinstance(decoder, TokenDecoder)

    def test_implements_health_checkable_protocol(self):
        """[CT] isinstance(decoder, HealthCheckable) is True."""
        mock_provider = AsyncMock()
        decoder = JWKSTokenDecoder(
            key_provider=mock_provider, issuer="test", allowed_clients=["test"]
        )
        assert isinstance(decoder, HealthCheckable)
