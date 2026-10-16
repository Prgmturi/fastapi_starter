"""Tests for JWKSManager — fetching and caching Keycloak's signing keys.

Module under test: src/fastapi_starter/core/auth/jwks_manager.py
Layer: Infrastructure adapter (fake Keycloak behind httpx.MockTransport)

WHY these tests exist: every authenticated request asks this class for a
key. They pin down the cache rules — when it fetches and what it raises —
so a change to those rules shows up as a failing test.
"""

import json

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from fastapi_starter.core.auth.jwks_manager import JWKSManager
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.protocols import KeyProvider


class FakeCertsEndpoint:
    """Keycloak's certs endpoint: serves a key set and records each request."""

    def __init__(self, public_key: rsa.RSAPublicKey, kids: list[str]) -> None:
        jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
        self.keys = [{**jwk, "kid": kid, "use": "sig", "alg": "RS256"} for kid in kids]
        self.requests: list[httpx.Request] = []
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"keys": self.keys})


@pytest.fixture(scope="module")
def rsa_private_key() -> rsa.RSAPrivateKey:
    """One key for the whole module: generating RSA keys is slow."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def keycloak_settings() -> KeycloakSettings:
    return KeycloakSettings(realm="test-realm", jwks_cache_ttl=3600)


@pytest.fixture
def certs(rsa_private_key) -> FakeCertsEndpoint:
    return FakeCertsEndpoint(rsa_private_key.public_key(), kids=["key-1"])


@pytest.fixture
async def jwks_manager(keycloak_settings, certs):
    """JWKSManager talking to the fake endpoint through an injected client."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(certs)) as client:
        yield JWKSManager(keycloak_settings, client)


class TestRefreshKeys:
    """JWKSManager.refresh_keys() — one request to the realm's certs URL."""

    async def test_fetches_the_realm_certs_url(
        self, jwks_manager, certs, keycloak_settings
    ):
        """[HP] Exactly one GET, to KeycloakSettings.certs_url."""
        await jwks_manager.refresh_keys()

        assert [str(request.url) for request in certs.requests] == [
            keycloak_settings.certs_url
        ]

    async def test_keycloak_unreachable_raises_runtime_error(self, jwks_manager, certs):
        """[EC] Network error -> RuntimeError, no httpx exception leaks."""
        certs.down = True

        with pytest.raises(RuntimeError, match="Failed to fetch JWKS"):
            await jwks_manager.refresh_keys()


class TestGetKey:
    """JWKSManager.get_key() — cached lookup by key ID."""

    async def test_first_call_fetches_then_serves_from_cache(self, jwks_manager, certs):
        """[HP] One fetch serves every lookup while the cache is valid."""
        first = await jwks_manager.get_key("key-1")
        second = await jwks_manager.get_key("key-1")

        assert first.key_id == "key-1"
        assert second is first
        assert len(certs.requests) == 1

    async def test_expired_cache_fetches_again(self, certs):
        """[EC] jwks_cache_ttl elapsed -> next lookup fetches fresh keys."""
        settings = KeycloakSettings(realm="test-realm", jwks_cache_ttl=0)

        async with httpx.AsyncClient(transport=httpx.MockTransport(certs)) as client:
            manager = JWKSManager(settings, client)
            await manager.get_key("key-1")
            await manager.get_key("key-1")

        assert len(certs.requests) == 2

    async def test_unknown_kid_fetches_once_more_then_raises(self, jwks_manager, certs):
        """[EC] kid not in the key set -> one extra fetch, then ValueError.

        WHY: an unknown kid may mean Keycloak rotated its keys, so the
        manager fetches again before giving up. NOTE: this happens for
        every unknown kid, including those of forged tokens.
        """
        with pytest.raises(ValueError, match="not found"):
            await jwks_manager.get_key("unknown-kid")

        assert len(certs.requests) == 2  # initial fetch + retry


class TestGetSigningKeyFromToken:
    """JWKSManager.get_signing_key_from_token() — kid from the JWT header."""

    async def test_returns_key_named_by_token_kid(self, jwks_manager, rsa_private_key):
        """[HP] Header kid selects the matching key."""
        token = pyjwt.encode(
            {"sub": "user-1"},
            rsa_private_key,
            algorithm="RS256",
            headers={"kid": "key-1"},
        )

        key = await jwks_manager.get_signing_key_from_token(token)

        assert key.key_id == "key-1"

    async def test_token_without_kid_raises_value_error(
        self, jwks_manager, rsa_private_key
    ):
        """[EC] No kid in the header -> ValueError."""
        token = pyjwt.encode({"sub": "user-1"}, rsa_private_key, algorithm="RS256")

        with pytest.raises(ValueError, match="no 'kid'"):
            await jwks_manager.get_signing_key_from_token(token)

    async def test_malformed_token_raises_value_error(self, jwks_manager):
        """[EC] Not a JWT -> ValueError, no PyJWT exception leaks."""
        with pytest.raises(ValueError, match="Invalid token format"):
            await jwks_manager.get_signing_key_from_token("not-a-jwt")


class TestHealthCheck:
    """JWKSManager.health_check() — is the certs endpoint reachable?"""

    async def test_true_when_certs_endpoint_answers(self, jwks_manager, certs):
        """[HP] 200 from Keycloak -> True."""
        assert await jwks_manager.health_check() is True
        assert len(certs.requests) == 1

    async def test_raises_when_keycloak_unreachable(self, jwks_manager, certs):
        """[EC] Network error propagates to the readiness probe."""
        certs.down = True

        with pytest.raises(httpx.ConnectError):
            await jwks_manager.health_check()


class TestKeyProviderProtocol:
    """Contract test: JWKSManager satisfies KeyProvider.

    WHY: JWKSTokenDecoder depends on the KeyProvider Protocol.
    """

    async def test_implements_key_provider_protocol(self, jwks_manager):
        """[CT] isinstance(manager, KeyProvider) is True."""
        assert isinstance(jwks_manager, KeyProvider)
