"""Tests for auth dependencies — get_current_user, require_roles."""

import pytest


class TestGetCurrentUser:
    """get_current_user dependency."""

    async def test_valid_token_returns_user(self):
        pytest.skip("Not implemented yet")

    async def test_missing_credentials_raises_401(self):
        pytest.skip("Not implemented yet")

    async def test_invalid_token_raises_401(self):
        pytest.skip("Not implemented yet")


class TestGetOptionalUser:
    """get_optional_user dependency."""

    async def test_valid_token_returns_user(self):
        pytest.skip("Not implemented yet")

    async def test_missing_credentials_returns_none(self):
        pytest.skip("Not implemented yet")

    async def test_invalid_token_returns_none(self):
        pytest.skip("Not implemented yet")


class TestRequireRoles:
    """require_roles factory — role-based access control."""

    async def test_user_with_required_role_passes(self):
        pytest.skip("Not implemented yet")

    async def test_user_without_required_role_raises_403(self):
        pytest.skip("Not implemented yet")

    async def test_multiple_roles_any_match(self):
        pytest.skip("Not implemented yet")

    async def test_string_roles_accepted(self):
        pytest.skip("Not implemented yet")
