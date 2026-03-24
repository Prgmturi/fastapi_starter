from fastapi_starter.core.auth.protocols import ClaimExtractor, TokenDecoder
from fastapi_starter.core.auth.schemas import User
from fastapi_starter.core.logging import get_logger
from fastapi_starter.core.protocols import HealthCheckable

logger = get_logger(__name__)


class AuthService:
    """
    Orchestrates token validation using injected ports.

    Depends only on Protocols — no PyJWT, no httpx, no Keycloak-specific logic.
    Implements the TokenValidator Protocol.

    To swap the JWT library or auth provider:
    - Provide a different TokenDecoder implementation
    - Provide a different ClaimExtractor implementation
    This class stays unchanged.
    """

    def __init__(
        self,
        decoder: TokenDecoder,
        extractor: ClaimExtractor,
        health_checker: HealthCheckable,
    ) -> None:
        self._decoder = decoder
        self._extractor = extractor
        self._health_checker = health_checker

    async def validate_token(self, token: str) -> User:
        """
        Validate token and return the authenticated user.

        Raises:
            UnauthorizedError: If the token is invalid, expired, or malformed.
        """
        claims = await self._decoder.decode(token)
        user = self._extractor.extract_user(claims)

        logger.debug(
            "token_validated",
            user_id=user.id,
            username=user.username,
            roles=[r.value for r in user.roles],
        )

        return user

    async def health_check(self) -> bool:
        """Check if the auth backend is reachable."""
        return await self._health_checker.health_check()
