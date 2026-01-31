from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.core.auth.service import AuthService
from fastapi_starter.core.exceptions import UnauthorizedError

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(request: Request) -> AuthService:
    """Get AuthService from app state."""
    return request.app.state.auth_service


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """
    Dependency that extracts and validates the current user.

    Raises:
        HTTPException 401: If no token or invalid token
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await auth_service.validate_token(credentials.credentials)
    return user


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
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


def require_roles(required_roles: list[str]):
    """
    Factory for role-based access control dependency.

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
    """

    async def role_checker(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not user.has_any_role(required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {required_roles}",
            )
        return user

    return role_checker


# Type aliases for common use cases
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]

# Role-specific aliases
AdminUser = Annotated[
    User, Depends(require_roles([RoleEnum.SUPERADMIN, RoleEnum.ADMIN]))
]
SuperAdminUser = Annotated[User, Depends(require_roles([RoleEnum.SUPERADMIN]))]
CollabUser = Annotated[User, Depends(require_roles([RoleEnum.COLLAB]))]

__all__ = [
    "get_auth_service",
    "get_current_user",
]
