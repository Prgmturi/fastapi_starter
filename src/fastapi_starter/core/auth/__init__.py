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
    OAuthProvider,
    TokenDecoder,
    TokenValidator,
)
from fastapi_starter.core.auth.schemas import RoleEnum, TokenResponse, User

__all__ = [
    # Protocols (auth-specific only; HealthCheckable/KeyProvider live in core.protocols)
    "TokenValidator",
    "TokenDecoder",
    "ClaimExtractor",
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
