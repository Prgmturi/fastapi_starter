"""Tests for JWKSManager — fetching and caching Keycloak's signing keys.

Module under test: src/fastapi_starter/adapters/keycloak/jwks_manager.py
Layer: Infrastructure adapter (fake Keycloak behind httpx.MockTransport)

WHY these tests exist: every authenticated request asks this class for a
key. They pin down the cache rules — when it fetches and what it raises —
so a change to those rules shows up as a failing test.
"""

import asyncio
import json

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from fastapi_starter.adapters.keycloak.jwks_manager import JWKSManager
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.exceptions import ServiceUnavailableError
from fastapi_starter.core.protocols import KeyProvider


class FakeCertsEndpoint:
    """Keycloak's certs endpoint: serves a key set and records each request."""

    def __init__(self, public_key: rsa.RSAPublicKey, kids: list[str]) -> None:
        self._jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
        self.serve(kids)
        self.requests: list[httpx.Request] = []
        self.down = False
        self.body: str | None = None

    def serve(self, kids: list[str]) -> None:
        """Publish these key IDs, as Keycloak does after a key rotation."""
        self.keys = [
            {**self._jwk, "kid": kid, "use": "sig", "alg": "RS256"} for kid in kids
        ]

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        # Hand control to the other tasks, as a real network call does:
        # that is when concurrent lookups pile up.
        await asyncio.sleep(0)
        if self.down:
            raise httpx.ConnectError("connection refused", request=request)
        if self.body is not None:
            return httpx.Response(200, text=self.body)
        return httpx.Response(200, json={"keys": self.keys})


class FakeClock:
    """Monotonic clock that moves only when the test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(scope="module")
def rsa_private_key() -> rsa.RSAPrivateKey:
    """One key for the whole module: generating RSA keys is slow."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def keycloak_settings() -> KeycloakSettings:
    return KeycloakSettings(
        realm="test-realm", jwks_cache_ttl=3600, jwks_min_refresh_interval=30
    )


@pytest.fixture
def certs(rsa_private_key) -> FakeCertsEndpoint:
    return FakeCertsEndpoint(rsa_private_key.public_key(), kids=["key-1"])


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def jwks_manager(keycloak_settings, certs, clock):
    """JWKSManager talking to the fake endpoint through an injected client."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(certs)) as client:
        yield JWKSManager(keycloak_settings, client, clock=clock)


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

    async def test_keycloak_unreachable_raises_service_unavailable(
        self, jwks_manager, certs
    ):
        """[EC] Network error -> ServiceUnavailableError (503), no httpx leak."""
        certs.down = True

        with pytest.raises(ServiceUnavailableError):
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

    async def test_expired_cache_fetches_again(self, jwks_manager, certs, clock):
        """[EC] jwks_cache_ttl elapsed -> next lookup fetches fresh keys."""
        await jwks_manager.get_key("key-1")
        clock.advance(3601)
        await jwks_manager.get_key("key-1")

        assert len(certs.requests) == 2

    async def test_unknown_kid_raises_without_refetching_at_once(
        self, jwks_manager, certs
    ):
        """[EC] kid missing from keys fetched a moment ago -> ValueError, 1 fetch.

        WHY: a refetch right away would not find it either. Before the
        limit, every unknown kid — those of forged tokens too — cost a
        second call to Keycloak.
        """
        with pytest.raises(ValueError, match="not found"):
            await jwks_manager.get_key("unknown-kid")

        assert len(certs.requests) == 1

    async def test_rotated_key_found_with_one_fetch(self, jwks_manager, certs, clock):
        """[HP] Keycloak rotated its keys -> the new kid is fetched and found.

        WHY: the limit on fetches must not block a real key rotation.
        """
        await jwks_manager.refresh_keys()
        certs.serve(["key-2"])
        clock.advance(31)

        key = await jwks_manager.get_key("key-2")

        assert key.key_id == "key-2"
        assert len(certs.requests) == 2


class TestFetchLimits:
    """How often Keycloak is called: one fetch at a time, and at most one
    every jwks_min_refresh_interval seconds.

    WHY: measured on 16 October 2026 — 25 tokens with invented kids cost 25
    calls to Keycloak, and so did 25 requests in flight as the cache expired.
    """

    async def test_invented_kids_fetch_at_most_once(self, jwks_manager, certs, clock):
        """[EC] 25 tokens with invented kids, one after another -> 1 extra fetch."""
        await jwks_manager.refresh_keys()
        clock.advance(31)  # past the interval: one refetch is allowed

        for i in range(25):
            with pytest.raises(ValueError, match="not found"):
                await jwks_manager.get_key(f"invented-{i}")

        assert len(certs.requests) == 2  # startup + one refetch

    async def test_concurrent_invented_kids_fetch_at_most_once(
        self, jwks_manager, certs, clock
    ):
        """[EC] 25 tokens with invented kids at the same time -> 1 extra fetch."""
        await jwks_manager.refresh_keys()
        clock.advance(31)

        results = await asyncio.gather(
            *(jwks_manager.get_key(f"invented-{i}") for i in range(25)),
            return_exceptions=True,
        )

        assert all(isinstance(result, ValueError) for result in results)
        assert len(certs.requests) == 2  # startup + one refetch

    async def test_concurrent_lookups_on_expired_cache_fetch_once(
        self, jwks_manager, certs, clock
    ):
        """[EC] 25 concurrent lookups as the cache expires -> 1 fetch."""
        await jwks_manager.refresh_keys()
        clock.advance(3601)

        keys = await asyncio.gather(*(jwks_manager.get_key("key-1") for _ in range(25)))

        assert {key.key_id for key in keys} == {"key-1"}
        assert len(certs.requests) == 2  # startup + one refresh


class TestKeycloakDown:
    """Keycloak unreachable — cached keys keep working, missing ones give 503.

    WHY: measured on 16 October 2026 — with Keycloak down and the cache
    expired, a valid token got 401 although its key was in the cache.
    A Keycloak restart must not log every user out.
    """

    async def test_cached_key_served_when_refresh_fails(
        self, jwks_manager, certs, clock
    ):
        """[EC] Cache expired, Keycloak down -> the cached key is returned."""
        await jwks_manager.refresh_keys()
        clock.advance(3601)
        certs.down = True

        key = await jwks_manager.get_key("key-1")

        assert key.key_id == "key-1"

    async def test_failed_fetch_retried_once_per_interval(
        self, jwks_manager, certs, clock
    ):
        """[EC] While Keycloak is down, at most one attempt per interval.

        WHY: otherwise every request would wait for a call bound to fail.
        """
        await jwks_manager.refresh_keys()
        clock.advance(3601)
        certs.down = True

        for _ in range(10):
            await jwks_manager.get_key("key-1")
        clock.advance(31)
        await jwks_manager.get_key("key-1")

        assert len(certs.requests) == 3  # startup, first attempt, retry

    async def test_body_that_is_not_a_key_set_counts_as_down(
        self, jwks_manager, certs, clock
    ):
        """[EC] 200 with an HTML page (a proxy error) -> cached key served."""
        await jwks_manager.refresh_keys()
        clock.advance(3601)
        certs.body = "<html>502 Bad Gateway</html>"

        key = await jwks_manager.get_key("key-1")

        assert key.key_id == "key-1"

    async def test_uncached_kid_raises_service_unavailable(
        self, jwks_manager, certs, clock
    ):
        """[EC] Keycloak down, kid not in the cache -> ServiceUnavailableError.

        WHY: the key may exist (a rotation not seen yet), so "invalid
        token" would be a guess. 503 tells the client to retry.
        """
        await jwks_manager.refresh_keys()
        clock.advance(31)
        certs.down = True

        with pytest.raises(ServiceUnavailableError):
            await jwks_manager.get_key("key-2")

    async def test_no_keys_yet_raises_service_unavailable(self, jwks_manager, certs):
        """[EC] Nothing fetched yet and Keycloak down -> ServiceUnavailableError."""
        certs.down = True

        with pytest.raises(ServiceUnavailableError):
            await jwks_manager.get_key("key-1")


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
    """JWKSManager.health_check() — can tokens be verified right now?

    WHY: the readiness probe calls it every few seconds on every instance.
    With Keycloak down the cached keys keep verifying tokens, so the check
    must not call Keycloak: otherwise every instance turns "not ready" at
    the same moment and the whole API goes down with it.
    """

    async def test_false_before_any_key_is_cached(self, jwks_manager, certs):
        """[EC] Nothing cached -> False, without calling Keycloak."""
        assert await jwks_manager.health_check() is False
        assert certs.requests == []

    async def test_true_with_cached_keys_and_keycloak_down(self, jwks_manager, certs):
        """[HP] Keys cached, Keycloak unreachable -> True, no request."""
        await jwks_manager.refresh_keys()
        certs.requests.clear()
        certs.down = True

        assert await jwks_manager.health_check() is True
        assert certs.requests == []

    async def test_true_once_the_cache_has_expired(
        self, jwks_manager, certs, clock, keycloak_settings
    ):
        """[EC] Past the TTL the old keys still verify tokens -> True, no request."""
        await jwks_manager.refresh_keys()
        certs.requests.clear()
        clock.advance(keycloak_settings.jwks_cache_ttl + 1)

        assert await jwks_manager.health_check() is True
        assert certs.requests == []


class TestKeyProviderProtocol:
    """Contract test: JWKSManager satisfies KeyProvider.

    WHY: JWKSTokenDecoder depends on the KeyProvider Protocol.
    """

    async def test_implements_key_provider_protocol(self, jwks_manager):
        """[CT] isinstance(manager, KeyProvider) is True."""
        assert isinstance(jwks_manager, KeyProvider)
