from typing import Any

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from fastapi_starter.core.exceptions import UnauthorizedError
from fastapi_starter.core.logging import get_logger
from fastapi_starter.core.protocols import KeyProvider

logger = get_logger(__name__)


class JWKSTokenDecoder:
    """
    JWT decoder backed by JWKS key fetching.

    Implements both TokenDecoder and HealthCheckable protocols.

    Responsibilities:
    - Fetches the signing key for the token's kid via a KeyProvider
    - Decodes and verifies the JWT (signature, expiry, issuer)
    - Converts all library exceptions (PyJWT) into domain UnauthorizedError

    No PyJWT types leak outside this class.
    """

    def __init__(self, key_provider: KeyProvider, issuer: str) -> None:
        self._key_provider = key_provider
        self._issuer = issuer

    async def decode(self, token: str) -> dict[str, Any]:
        """
        Decode and verify JWT token.

        Returns:
            Raw claims dict on success.

        Raises:
            UnauthorizedError: On any failure (expired, invalid, key not found).
        """
        try:
            signing_key = await self._key_provider.get_signing_key_from_token(token)

            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={
                    "verify_aud": False,
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
            logger.warning("token_validation_failed", error=str(e))
            raise UnauthorizedError(str(e)) from e

        except Exception as e:
            logger.error("unexpected_decode_error", error=str(e), exc_info=True)
            raise UnauthorizedError("Authentication failed") from e

    async def health_check(self) -> bool:
        """Delegate health check to the underlying key provider."""
        return await self._key_provider.health_check()
