import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import ValidationError as PydanticValidationError

from fastapi_starter.core.auth.jwks import JWKSManager
from fastapi_starter.core.auth.schemas import TokenPayload, User
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.exceptions import UnauthorizedError
from fastapi_starter.core.logging import get_logger

logger = get_logger(__name__)


class AuthService:
    def __init__(self, settings: KeycloakSettings, jwks_manager: JWKSManager) -> None:
        self._settings = settings
        self._jwks_manager = jwks_manager

    @property
    def issuer(self) -> str:
        """Expected token issuer."""
        return f"{self._settings.server_url}/realms/{self._settings.realm}"

    async def initialize(self) -> None:
        """
        Initialize the service.

        Pre-fetches JWKS keys. Call once at application startup.
        """
        await self._jwks_manager.refresh_keys()
        logger.info("auth_service_initialized", issuer=self.issuer)

    async def validate_token(self, token: str) -> User:
        try:
            signing_key = await self._jwks_manager.get_signing_key_from_token(token)

            # Decode and validate
            payload_dict = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={
                    "verify_aud": False,  # Keycloak audience can be complex
                    "verify_exp": True,
                    "verify_iss": True,
                },
            )

            # Parse payload
            payload = TokenPayload.model_validate(payload_dict)

            # Extract user
            user = self._extract_user(payload)

            logger.debug(
                "token_validated",
                user_id=user.id,
                username=user.username,
                roles=user.roles,
            )

            return user

        except ExpiredSignatureError:
            logger.warning("token_expired")
            raise UnauthorizedError("Token expired") from None

        except InvalidTokenError as e:
            logger.warning("token_invalid", error=str(e))
            raise UnauthorizedError("Invalid token") from None

        except ValueError as e:
            logger.warning("token_validation_failed", error=str(e))
            raise UnauthorizedError(str(e)) from None

        except PydanticValidationError as e:
            logger.warning("token_payload_invalid", error=str(e))
            raise UnauthorizedError("Invalid token format") from None

        except Exception as e:
            logger.error("unexpected_auth_error", error=str(e), exc_info=True)
            raise UnauthorizedError("Authentication failed") from None

    def _extract_user(self, payload: TokenPayload) -> User:
        """
        Extract User object from token payload.

        Consolidates roles from realm_access and resource_access.
        """
        roles: list[str] = []

        # Realm-level roles
        if payload.realm_access and "roles" in payload.realm_access:
            roles.extend(payload.realm_access["roles"])

        # Client-level roles (optional)
        if payload.resource_access:
            client_id = self._settings.client_id
            if client_id in payload.resource_access:
                client_roles = payload.resource_access[client_id].get("roles", [])
                roles.extend(client_roles)

        # Remove duplicates, keep order
        unique_roles = list(dict.fromkeys(roles))

        return User(
            id=payload.sub,
            username=payload.preferred_username or payload.sub,
            email=payload.email,
            email_verified=payload.email_verified,
            first_name=payload.given_name,
            last_name=payload.family_name,
            roles=unique_roles,
        )

    async def health_check(self) -> bool:
        """
        Check if auth service is operational.

        Returns:
            True if Keycloak is reachable.

        Raises:
            httpx.HTTPError: If Keycloak is unreachable.
        """
        return await self._jwks_manager.health_check()
