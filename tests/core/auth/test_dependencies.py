"""Tests for auth dependencies — get_current_user, require_roles.

Module under test: src/fastapi_starter/core/auth/dependencies.py
Layer: FastAPI integration (test dependency functions directly)

WHY these tests exist: These dependencies are the gateway to every
protected endpoint. If get_current_user fails, no endpoint is accessible.
If require_roles fails, unauthorized users access admin endpoints.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from fastapi_starter.core.auth.dependencies import (
    get_current_user,
    get_optional_user,
    require_roles,
)
from fastapi_starter.core.auth.schemas import RoleEnum
from fastapi_starter.core.exceptions import UnauthorizedError


class TestGetCurrentUser:
    """get_current_user dependency."""

    async def test_valid_token_returns_user(self, sample_user):
        """[HP] Valid token -> User returned."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="valid-token",
        )
        auth_service = AsyncMock()
        auth_service.validate_token.return_value = sample_user

        user = await get_current_user(credentials, auth_service)

        assert user == sample_user
        auth_service.validate_token.assert_called_once_with("valid-token")

    async def test_missing_credentials_raises_401(self):
        """[EC] No token -> HTTPException 401."""
        auth_service = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None, auth_service)

        assert exc_info.value.status_code == 401

    async def test_invalid_token_raises_401(self):
        """[EC] Invalid token -> UnauthorizedError propagates."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="bad-token",
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
            scheme="Bearer", credentials="valid-token",
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
            scheme="Bearer", credentials="bad-token",
        )
        auth_service = AsyncMock()
        auth_service.validate_token.side_effect = UnauthorizedError("expired")

        user = await get_optional_user(credentials, auth_service)

        assert user is None


class TestRequireRoles:
    """require_roles factory — role-based access control."""

    async def test_user_with_required_role_passes(self, sample_admin_user):
        """[HP] User has the required role -> returns user."""
        role_checker = require_roles([RoleEnum.ADMIN])

        # Simulate FastAPI calling the inner function with a resolved user
        result = await role_checker(user=sample_admin_user)

        assert result == sample_admin_user

    async def test_user_without_required_role_raises_403(self, sample_user):
        """[EC] User lacks the required role -> HTTPException 403."""
        role_checker = require_roles([RoleEnum.ADMIN])

        with pytest.raises(HTTPException) as exc_info:
            await role_checker(user=sample_user)

        assert exc_info.value.status_code == 403

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
