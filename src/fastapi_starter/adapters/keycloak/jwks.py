from collections.abc import Collection
from typing import Any

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from fastapi_starter.core.exceptions import AppExceptionError, UnauthorizedError
from fastapi_starter.core.logging import get_logger
from fastapi_starter.core.protocols import KeyProvider

logger = get_logger(__name__)

# Keycloak writes what a token is for in its "typ" claim: "Bearer" for access
# tokens, "ID" for ID tokens, "Refresh" and "Offline" for refresh tokens.
# All of them are signed with the same realm keys.
ACCESS_TOKEN_TYPE = "Bearer"

# Seconds of difference tolerated between Keycloak's clock and this
# server's, when checking exp and iat.
CLOCK_SKEW_LEEWAY = 30

# Claims a token must carry. PyJWT checks exp only when it is present, so
# without this a signed token lacking exp would never expire. sub is the
# user's id: every request needs it.
REQUIRED_CLAIMS = ["exp", "iat", "iss", "sub"]


class JWKSTokenDecoder:
    """
    JWT decoder backed by JWKS key fetching.

    Implements both TokenDecoder and HealthCheckable protocols.

    Responsibilities:
    - Fetches the signing key for the token's kid via a KeyProvider
    - Decodes and verifies the JWT (signature, expiry, issuer, required
      claims, audience when configured)
    - Accepts only access tokens issued to the allowed clients (typ, azp)
    - Converts all library exceptions (PyJWT) into domain UnauthorizedError

    No PyJWT types leak outside this class.
    """

    def __init__(
        self,
        key_provider: KeyProvider,
        issuer: str,
        allowed_clients: Collection[str],
        audience: str | None = None,
    ) -> None:
        """
        Args:
            key_provider: Source of the realm's public keys.
            issuer: Expected iss claim, the realm URL.
            allowed_clients: Clients whose access tokens are accepted (azp).
            audience: Expected aud claim. None: aud is not checked.
        """
        self._key_provider = key_provider
        self._issuer = issuer
        self._allowed_clients = tuple(allowed_clients)
        self._audience = audience

    async def decode(self, token: str) -> dict[str, Any]:
        """
        Decode and verify JWT token.

        Returns:
            Raw claims dict on success.

        Raises:
            UnauthorizedError: On any failure (expired, invalid, key not found,
                not an access token, issued to a client not allowed).
        """
        claims = await self._verify(token)

        # Checked after the signature: only then do the claims come from
        # Keycloak. Every rejection gets the same message; the reason goes
        # to the log.
        if claims.get("typ") != ACCESS_TOKEN_TYPE:
            logger.warning("token_type_rejected", typ=claims.get("typ"))
            raise UnauthorizedError("Invalid token")

        if claims.get("azp") not in self._allowed_clients:
            logger.warning("token_client_rejected", azp=claims.get("azp"))
            raise UnauthorizedError("Invalid token")

        return claims

    async def _verify(self, token: str) -> dict[str, Any]:
        """Verify signature and standard claims. Every failure becomes a 401."""
        try:
            signing_key = await self._key_provider.get_signing_key_from_token(token)

            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=CLOCK_SKEW_LEEWAY,
                options={
                    "require": REQUIRED_CLAIMS,
                    "verify_aud": self._audience is not None,
                    "verify_exp": True,
                    "verify_iss": True,
                },
            )

        except ExpiredSignatureError as e:
            logger.warning("token_expired")
            raise UnauthorizedError("Token expired") from e

        except InvalidTokenError as e:
            logger.warning("token_invalid", error=str(e))
            raise UnauthorizedError("Invalid token") from e

        except ValueError as e:
            # The text can contain what the caller sent (an unknown kid):
            # it goes to the log, the response says only "Invalid token".
            logger.warning("token_validation_failed", error=str(e))
            raise UnauthorizedError("Invalid token") from e

        except AppExceptionError:
            # Raised on purpose by the key provider, such as a 503 when
            # Keycloak is unreachable. The catch-all below would turn it
            # into a 401 and send the user back to the login.
            raise

        except Exception as e:
            logger.error("unexpected_decode_error", error=str(e), exc_info=True)
            raise UnauthorizedError("Authentication failed") from e

    async def health_check(self) -> bool:
        """True while the key provider can hand out signing keys."""
        return await self._key_provider.health_check()
