from fastapi_starter.core.auth.dependencies import (
    AdminUser,
    CollabUser,
    CurrentUser,
    OptionalUser,
    SuperAdminUser,
    get_auth_service,
    require_roles,
)
from fastapi_starter.core.auth.protocols import (
    ClaimExtractor,
    HealthCheckable,
    KeyProvider,
    OAuthProvider,
    TokenDecoder,
    TokenValidator,
)
from fastapi_starter.core.auth.schemas import RoleEnum, TokenResponse, User

__all__ = [
    # Protocols
    "TokenValidator",
    "TokenDecoder",
    "ClaimExtractor",
    "HealthCheckable",
    "KeyProvider",
    "OAuthProvider",
    # Schemas
    "User",
    "TokenResponse",
    "RoleEnum",
    # Dependencies
    "get_auth_service",
    "CurrentUser",
    "OptionalUser",
    "AdminUser",
    "SuperAdminUser",
    "CollabUser",
    "require_roles",
]
