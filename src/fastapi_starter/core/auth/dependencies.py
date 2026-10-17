from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from fastapi_starter.core.auth.protocols import TokenValidator
from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.core.exceptions import ForbiddenError, UnauthorizedError

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(request: Request) -> TokenValidator:
    """Get TokenValidator from app state."""
    service: TokenValidator = request.app.state.auth_service
    return service


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    auth_service: Annotated[TokenValidator, Depends(get_auth_service)],
) -> User:
    """
    Dependency that extracts and validates the current user.

    Raises:
        UnauthorizedError: If no token or invalid token (401)
    """
    if credentials is None:
        raise UnauthorizedError("Not authenticated")

    user = await auth_service.validate_token(credentials.credentials)
    return user


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    auth_service: Annotated[TokenValidator, Depends(get_auth_service)],
) -> User | None:
    """
    Dependency that extracts user if token present, None otherwise.

    Use for endpoints that work differently for authenticated users.
    """
    if credentials is None:
        return None

    try:
        return await auth_service.validate_token(credentials.credentials)
    except UnauthorizedError:
        return None


def require_roles(
    required_roles: list[RoleEnum | str],
) -> Callable[..., Coroutine[Any, Any, User]]:
    """
    Factory for role-based access control dependency.

    The user needs at least one of the listed roles. Only the listed roles
    count: the hierarchy is spelled out in the aliases below.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_roles([RoleEnum.ADMIN]))])
        async def admin_endpoint():
            ...

    Or with user access:
        @router.get("/admin")
        async def admin_endpoint(user: Annotated[
                User,
                Depends(require_roles([RoleEnum.ADMIN]))]):
            return user

    Raises:
        ValueError: If the list is empty or names a role that does not exist
    """
    if not required_roles:
        raise ValueError("require_roles needs at least one role")
    # Converted now, when the module that defines the route is imported:
    # RoleEnum("manger") raises ValueError, so a misspelled role stops the
    # app at startup instead of answering 500 to every request.
    allowed: list[RoleEnum | str] = [RoleEnum(role) for role in required_roles]

    async def role_checker(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not user.has_any_role(allowed):
            # "Permission denied" only: the roles that would let the user in
            # are not the client's business.
            raise ForbiddenError()
        return user

    return role_checker


# Type aliases for common use cases
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]

# Role-specific aliases. The roles form a hierarchy, highest first:
# superadmin > admin > collaborator. Each alias lets through its role and
# every role above it. "user" is not part of the hierarchy.
SuperAdminUser = Annotated[User, Depends(require_roles([RoleEnum.SUPERADMIN]))]
AdminUser = Annotated[
    User, Depends(require_roles([RoleEnum.SUPERADMIN, RoleEnum.ADMIN]))
]
CollabUser = Annotated[
    User,
    Depends(require_roles([RoleEnum.SUPERADMIN, RoleEnum.ADMIN, RoleEnum.COLLAB])),
]

__all__ = [
    "get_auth_service",
    "get_current_user",
    "get_optional_user",
    "require_roles",
    "CurrentUser",
    "OptionalUser",
    "AdminUser",
    "SuperAdminUser",
    "CollabUser",
]
