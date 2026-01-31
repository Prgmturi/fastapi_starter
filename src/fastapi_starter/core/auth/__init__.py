from fastapi_starter.core.auth.dependencies import (
    AdminUser,
    CollabUser,
    CurrentUser,
    OptionalUser,
    SuperAdminUser,
    require_roles,
)
from fastapi_starter.core.auth.schemas import RoleEnum, TokenPayload, User
from fastapi_starter.core.auth.service import AuthService

__all__ = [
    # Service
    "AuthService",
    "AuthenticationError",
    # Schemas
    "User",
    "TokenPayload",
    "RoleEnum",
    # Dependencies
    "CurrentUser",
    "OptionalUser",
    "AdminUser",
    "SuperAdminUser",
    "CollabUser",
    "get_auth_service",
    "require_roles",
]
