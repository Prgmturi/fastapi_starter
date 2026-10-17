"""Tests for auth dependencies — get_current_user, require_roles.

Module under test: src/fastapi_starter/core/auth/dependencies.py
Layer: FastAPI integration (test dependency functions directly)

WHY these tests exist: These dependencies are the gateway to every
protected endpoint. If get_current_user fails, no endpoint is accessible.
If require_roles fails, unauthorized users access admin endpoints.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from fastapi_starter.core.auth.dependencies import (
    AdminUser,
    CollabUser,
    SuperAdminUser,
    get_current_user,
    get_optional_user,
    require_roles,
)
from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.core.exceptions import (
    ForbiddenError,
    ServiceUnavailableError,
    UnauthorizedError,
)


class TestGetCurrentUser:
    """get_current_user dependency."""

    async def test_valid_token_returns_user(self, sample_user):
        """[HP] Valid token -> User returned."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token",
        )
        auth_service = AsyncMock()
        auth_service.validate_token.return_value = sample_user

        user = await get_current_user(credentials, auth_service)

        assert user == sample_user
        auth_service.validate_token.assert_called_once_with("valid-token")

    async def test_missing_credentials_raises_401(self):
        """[EC] No token -> UnauthorizedError, like an invalid token.

        WHY: both 401s go through the same handler, so they have the same
        body and the same WWW-Authenticate header.
        """
        auth_service = AsyncMock()

        with pytest.raises(UnauthorizedError) as exc_info:
            await get_current_user(None, auth_service)

        assert exc_info.value.status_code == 401
        assert exc_info.value.message == "Not authenticated"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    async def test_invalid_token_raises_401(self):
        """[EC] Invalid token -> UnauthorizedError propagates."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bad-token",
        )
        auth_service = AsyncMock()
        auth_service.validate_token.side_effect = UnauthorizedError("expired")

        with pytest.raises(UnauthorizedError):
            await get_current_user(credentials, auth_service)


class TestGetOptionalUser:
    """get_optional_user dependency."""

    async def test_valid_token_returns_user(self, sample_user):
        """[HP] Valid token -> User returned."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token",
        )
        auth_service = AsyncMock()
        auth_service.validate_token.return_value = sample_user

        user = await get_optional_user(credentials, auth_service)

        assert user == sample_user

    async def test_missing_credentials_returns_none(self):
        """[EC] No token -> None (not an error)."""
        auth_service = AsyncMock()

        user = await get_optional_user(None, auth_service)

        assert user is None

    async def test_invalid_token_returns_none(self):
        """[EC] Invalid token -> None (graceful degradation)."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="bad-token",
        )
        auth_service = AsyncMock()
        auth_service.validate_token.side_effect = UnauthorizedError("expired")

        user = await get_optional_user(credentials, auth_service)

        assert user is None

    async def test_backend_unavailable_propagates(self):
        """[EC] Auth backend unreachable -> ServiceUnavailableError, not None.

        WHY: None means "anonymous". An outage must not quietly turn a
        logged-in user into a guest: the client gets 503 and retries.
        """
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="valid-token",
        )
        auth_service = AsyncMock()
        auth_service.validate_token.side_effect = ServiceUnavailableError("auth")

        with pytest.raises(ServiceUnavailableError):
            await get_optional_user(credentials, auth_service)


class TestRequireRoles:
    """require_roles factory — role-based access control."""

    async def test_user_with_required_role_passes(self, sample_admin_user):
        """[HP] User has the required role -> returns user."""
        role_checker = require_roles([RoleEnum.ADMIN])

        # Simulate FastAPI calling the inner function with a resolved user
        result = await role_checker(user=sample_admin_user)

        assert result == sample_admin_user

    async def test_user_without_required_role_raises_403(self, sample_user):
        """[EC] User lacks the required role -> ForbiddenError (403)."""
        role_checker = require_roles([RoleEnum.ADMIN])

        with pytest.raises(ForbiddenError) as exc_info:
            await role_checker(user=sample_user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.message == "Permission denied"

    async def test_multiple_roles_any_match(self, sample_admin_user):
        """[HP] User has any one of the required roles -> passes."""
        role_checker = require_roles([RoleEnum.SUPERADMIN, RoleEnum.ADMIN])

        result = await role_checker(user=sample_admin_user)

        assert result == sample_admin_user

    async def test_string_roles_accepted(self, sample_admin_user):
        """[HP] String role values work (e.g., 'admin')."""
        role_checker = require_roles(["admin"])

        result = await role_checker(user=sample_admin_user)

        assert result == sample_admin_user

    def test_unknown_role_fails_when_the_dependency_is_built(self):
        """[EC] A misspelled role -> ValueError from require_roles itself.

        WHY: require_roles runs when the module that defines the route is
        imported, so the typo stops the app at startup. Before, the string
        was converted at every request, and every request answered 500.
        """
        with pytest.raises(ValueError, match="manger"):
            require_roles(["manger"])

    def test_no_roles_fails_when_the_dependency_is_built(self):
        """[EC] require_roles([]) -> ValueError: it would let nobody in."""
        with pytest.raises(ValueError, match="at least one role"):
            require_roles([])


class TestRoleAliases:
    """SuperAdminUser, AdminUser and CollabUser, through real routes.

    WHY: decision 4 of the roadmap (16 October 2026). The roles form a
    hierarchy, superadmin > admin > collaborator: each alias lets through
    its role and every role above it. "user" is not part of it. Before,
    an admin or a superadmin got 403 from a CollabUser route.
    """

    # Who passes each alias, as in the table of decision 4.
    ALLOWED = {
        "/roles/superadmin": {RoleEnum.SUPERADMIN},
        "/roles/admin": {RoleEnum.SUPERADMIN, RoleEnum.ADMIN},
        "/roles/collab": {RoleEnum.SUPERADMIN, RoleEnum.ADMIN, RoleEnum.COLLAB},
    }

    @pytest.fixture(autouse=True)
    def routes(self, app):
        @app.get("/roles/superadmin")
        async def superadmin(user: SuperAdminUser) -> dict[str, str]:
            return {"id": user.id}

        @app.get("/roles/admin")
        async def admin(user: AdminUser) -> dict[str, str]:
            return {"id": user.id}

        @app.get("/roles/collab")
        async def collab(user: CollabUser) -> dict[str, str]:
            return {"id": user.id}

    @pytest.fixture
    def login_as(self, app):
        """Make the requests come from a user who holds only this role."""

        def login(role: RoleEnum) -> None:
            user = User(id="user-1", username="someone", roles=[role])
            app.dependency_overrides[get_current_user] = lambda: user

        return login

    @pytest.mark.parametrize("path", ALLOWED)
    @pytest.mark.parametrize("role", list(RoleEnum))
    async def test_alias_lets_through_its_role_and_those_above(
        self, client, login_as, path, role
    ):
        """[HP] 200 for the roles in ALLOWED[path], 403 for the others."""
        login_as(role)

        response = await client.get(path)

        assert response.status_code == (200 if role in self.ALLOWED[path] else 403)

    async def test_denial_names_no_role(self, client, login_as):
        """[EC] The 403 says "Permission denied" and nothing else.

        WHY: the detail was "Required roles: [<RoleEnum.SUPERADMIN:
        'superadmin'>, <RoleEnum.ADMIN: 'admin'>]", so any caller learned
        the internal role names. The denial is still in the log, with the
        path (app_exception).
        """
        login_as(RoleEnum.USER)

        response = await client.get("/roles/admin")

        assert response.status_code == 403
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json() == {
            "type": "about:blank",
            "title": "Forbidden",
            "status": 403,
            "detail": "Permission denied",
        }
