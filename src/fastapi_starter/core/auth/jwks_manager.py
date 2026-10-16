import asyncio
import time
from collections.abc import Callable

import httpx
import jwt
from jwt import PyJWK, PyJWKSet
from jwt.exceptions import PyJWKSetError

from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.exceptions import ServiceUnavailableError
from fastapi_starter.core.logging import get_logger

logger = get_logger(__name__)


class JWKSManager:
    """Keycloak's signing keys, fetched on demand and kept in a cache.

    Rules, so that Keycloak gets few calls and a short outage does not log
    every user out:
    - one fetch at a time: concurrent lookups share it
    - at most one fetch every jwks_min_refresh_interval seconds, whatever
      the reason (expired cache, unknown kid, failed attempt)
    - when a fetch fails, the keys already in the cache keep working
    """

    def __init__(
        self,
        settings: KeycloakSettings,
        http_client: httpx.AsyncClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        Args:
            settings: Keycloak realm and key cache configuration.
            http_client: Client for the calls to Keycloak. The caller owns it
                and closes it at shutdown (see lifespan in main.py).
            clock: Seconds from an arbitrary origin. Monotonic by default, so
                a change of the system clock cannot expire or extend the
                cache. Tests pass a fake one.
        """
        self._settings = settings
        self._client = http_client
        self._clock = clock
        self._jwks: PyJWKSet | None = None
        self._fetched_at: float | None = None  # last successful fetch
        self._attempted_at: float | None = None  # last fetch, failed or not
        self._last_fetch_failed = False
        self._lock = asyncio.Lock()

    @property
    def jwks_url(self) -> str:
        """JWKS endpoint URL."""
        return self._settings.certs_url

    def _is_cache_valid(self) -> bool:
        """Check if cached keys are still valid."""
        if self._jwks is None or self._fetched_at is None:
            return False
        return self._clock() - self._fetched_at < self._settings.jwks_cache_ttl

    def _fetched_recently(self) -> bool:
        """True while the last attempt is too recent for a new one."""
        if self._attempted_at is None:
            return False
        elapsed = self._clock() - self._attempted_at
        return elapsed < self._settings.jwks_min_refresh_interval

    async def refresh_keys(self) -> None:
        """
        Fetch fresh keys from Keycloak.

        Called at startup; lookups refresh the cache on their own.

        Raises:
            ServiceUnavailableError: If Keycloak does not answer with a key set.
        """
        async with self._lock:
            if not await self._fetch():
                raise ServiceUnavailableError("auth")

    async def _fetch(self) -> bool:
        """Download the key set once. The caller holds the lock.

        Returns:
            True if the cache now holds fresh keys. On failure the keys
            already cached, if any, stay.
        """
        logger.debug("jwks_refresh_started", url=self.jwks_url)
        self._attempted_at = self._clock()

        try:
            response = await self._client.get(self.jwks_url)
            response.raise_for_status()
            jwks = PyJWKSet.from_dict(response.json())
        except (httpx.HTTPError, ValueError, PyJWKSetError) as e:
            # ValueError: the body is not JSON (a proxy error page, say).
            # PyJWKSetError: it is JSON, but holds no usable key.
            self._last_fetch_failed = True
            logger.error("jwks_refresh_failed", error=str(e))
            return False

        self._jwks = jwks
        self._fetched_at = self._clock()
        self._last_fetch_failed = False
        logger.info("jwks_refresh_completed", key_count=len(jwks.keys))
        return True

    def _find_key(self, kid: str) -> PyJWK | None:
        """Search for a key by ID in the cached JWKS."""
        if self._jwks is None:
            return None
        for jwk in self._jwks.keys:
            if jwk.key_id == kid:
                return jwk
        return None

    async def get_key(self, kid: str) -> PyJWK:
        """
        Get public key by key ID.

        Args:
            kid: Key ID from JWT header

        Returns:
            Public key for signature verification

        Raises:
            ValueError: If Keycloak's key set has no key with this ID.
            ServiceUnavailableError: If the key is not cached and Keycloak
                cannot be reached to look for it.
        """
        if not self._is_cache_valid():
            await self._refresh_expired_cache()

        key = self._find_key(kid)
        if key is None:
            key = await self._find_after_refetch(kid)
        return key

    async def _refresh_expired_cache(self) -> None:
        """Refetch an expired cache. If that fails, the old keys stay."""
        if self._jwks is not None and self._lock.locked():
            # Another lookup is already fetching: answer with the cached
            # keys instead of waiting for Keycloak.
            return

        async with self._lock:
            # A lookup that waited for the lock finds the work done.
            if self._is_cache_valid() or self._fetched_recently():
                return
            if not await self._fetch() and self._jwks is not None:
                logger.warning("jwks_using_cached_keys")

    async def _find_after_refetch(self, kid: str) -> PyJWK:
        """Look for a kid missing from the cache.

        Keycloak may have rotated its keys, so the key set is fetched again
        — at most once per interval, so that tokens with invented kids
        cannot cost a call to Keycloak each.
        """
        async with self._lock:
            # Another lookup may have refetched while this one waited.
            key = self._find_key(kid)
            if key is None and not self._fetched_recently():
                logger.warning("jwks_key_not_found_retrying", kid=kid)
                await self._fetch()
                key = self._find_key(kid)

        if key is not None:
            return key

        if self._last_fetch_failed:
            # Keycloak is unreachable: the key may exist and there is no
            # way to tell. 503, so the client retries instead of logging out.
            raise ServiceUnavailableError("auth")

        logger.warning("jwks_key_not_found", kid=kid)
        raise ValueError(f"Key {kid} not found in JWKS")

    async def get_signing_key_from_token(self, token: str) -> PyJWK:
        """
        Extract key ID from token and fetch corresponding key.

        Args:
            token: JWT token string

        Returns:
            Public key for this token

        Raises:
            ValueError: If the token is not a JWT or has no kid, or if
                Keycloak's key set has no key with that kid.
            ServiceUnavailableError: If Keycloak is needed and unreachable.
        """
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            if not kid:
                raise ValueError("Token has no 'kid' in header")

            return await self.get_key(kid)

        except jwt.exceptions.DecodeError as e:
            raise ValueError(f"Invalid token format: {e}") from e

    async def health_check(self) -> bool:
        """
        Verify Keycloak is reachable.

        Returns:
            True if Keycloak JWKS endpoint responds.

        Raises:
            httpx.HTTPError: If Keycloak is unreachable.
        """
        response = await self._client.get(self.jwks_url)
        response.raise_for_status()
        return True
