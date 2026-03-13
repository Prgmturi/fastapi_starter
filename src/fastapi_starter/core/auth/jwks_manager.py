import time
from typing import Any

import httpx
import jwt
from jwt import PyJWK, PyJWKSet

from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.logging import get_logger

logger = get_logger(__name__)


class JWKSManager:
    def __init__(self, settings: KeycloakSettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)
        self._jwks: PyJWKSet | None = None
        self._last_refresh: float = 0

    @property
    def jwks_url(self) -> str:
        """JWKS endpoint URL."""
        return self._settings.certs_url

    def _is_cache_valid(self) -> bool:
        """Check if cached keys are still valid."""
        if self._jwks is None:
            return False
        return (time.time() - self._last_refresh) < self._settings.jwks_cache_ttl

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def refresh_keys(self) -> None:
        """
        Fetch fresh keys from Keycloak.

        Called automatically when cache expires or key not found.
        """
        logger.debug("jwks_refresh_started", url=self.jwks_url)

        try:
            response = await self._client.get(self.jwks_url)
            response.raise_for_status()
            jwks_data = response.json()

            self._jwks = PyJWKSet.from_dict(jwks_data)
            self._last_refresh = time.time()

            key_count = len(jwks_data.get("keys", []))
            logger.info("jwks_refresh_completed", key_count=key_count)

        except httpx.HTTPError as e:
            logger.error("jwks_refresh_failed", error=str(e))
            raise RuntimeError(f"Failed to fetch JWKS: {e}") from e

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
            ValueError: If key not found after retry
        """
        if not self._is_cache_valid():
            await self.refresh_keys()

        # First attempt
        key = self._find_key(kid)
        if key is not None:
            return key

        # Key not found - maybe Keycloak rotated keys, try refreshing once
        logger.warning("jwks_key_not_found_retrying", kid=kid)
        await self.refresh_keys()

        key = self._find_key(kid)
        if key is not None:
            return key

        logger.error("jwks_key_not_found", kid=kid)
        raise ValueError(f"Key {kid} not found in JWKS")

    async def get_signing_key_from_token(self, token: str) -> PyJWK:
        """
        Extract key ID from token and fetch corresponding key.

        Args:
            token: JWT token string

        Returns:
            Public key for this token
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
