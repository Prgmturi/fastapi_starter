"""Tests for auth router — /auth/* endpoints.

Module under test: src/fastapi_starter/features/auth/router.py
Layer: HTTP endpoints (TestClient with mocked OAuthProvider)

WHY these tests exist: Auth endpoints are the public API surface for the
OAuth flow. We verify correct HTTP status codes, request validation, and
response structure.
"""

import pytest


class TestGetLoginUrl:
    """GET /auth/login — build authorization URL.

    WHY: First step of OAuth flow. We verify the endpoint delegates
    to OAuthProvider.build_authorization_url and returns the URL
    in the correct response format.
    """

    async def test_returns_authorization_url(self):
        """[HP] Returns 200 with authorization_url in response."""
        pytest.skip("Not implemented yet")

    async def test_missing_redirect_uri_returns_422(self):
        """[EC] Required query param missing -> 422."""
        pytest.skip("Not implemented yet")

    async def test_missing_code_challenge_returns_422(self):
        """[EC] Required query param missing -> 422."""
        pytest.skip("Not implemented yet")

    async def test_optional_state_passed_to_provider(self):
        """[HP] state param forwarded to build_authorization_url."""
        pytest.skip("Not implemented yet")


class TestExchangeToken:
    """POST /auth/token — exchange authorization code for tokens.

    WHY: Critical OAuth step. We verify:
    1. Success returns token structure
    2. Invalid code returns 401 (not 500)
    3. Request validation catches missing fields
    """

    async def test_valid_code_returns_tokens(self):
        """[HP] Valid request -> 200 with access_token + refresh_token."""
        pytest.skip("Not implemented yet")

    async def test_invalid_code_returns_error(self):
        """[EC] OAuthProvider raises UnauthorizedError -> propagated."""
        pytest.skip("Not implemented yet")

    async def test_missing_code_verifier_returns_422(self):
        """[EC] Request body missing code_verifier -> 422."""
        pytest.skip("Not implemented yet")

    async def test_short_code_verifier_returns_422(self):
        """[EC] code_verifier < 43 chars -> 422 (PKCE spec minimum)."""
        pytest.skip("Not implemented yet")


class TestRefreshToken:
    """POST /auth/refresh — token renewal.

    WHY: Client uses this to get new tokens before access_token expires.
    """

    async def test_valid_refresh_returns_new_tokens(self):
        """[HP] Valid refresh_token -> 200 with new tokens."""
        pytest.skip("Not implemented yet")

    async def test_invalid_refresh_token_returns_error(self):
        """[EC] OAuthProvider raises UnauthorizedError -> propagated."""
        pytest.skip("Not implemented yet")

    async def test_missing_refresh_token_returns_422(self):
        """[EC] Empty body -> 422."""
        pytest.skip("Not implemented yet")


class TestLogout:
    """POST /auth/logout — token revocation.

    WHY: Security requirement. User must be able to invalidate tokens.
    """

    async def test_successful_logout_returns_message(self):
        """[HP] Logout succeeds -> 200 with success message."""
        pytest.skip("Not implemented yet")

    async def test_missing_refresh_token_returns_422(self):
        """[EC] Empty body -> 422."""
        pytest.skip("Not implemented yet")


class TestGetMe:
    """GET /auth/me — current user information.

    WHY: Frontend calls this to get user profile after login.
    Must require authentication and return correct user structure.
    """

    async def test_authenticated_returns_user_info(self):
        """[HP] Authenticated request -> 200 with user details."""
        pytest.skip("Not implemented yet")

    async def test_response_includes_all_user_fields(self):
        """[HP] Response includes id, username, email, roles, full_name."""
        pytest.skip("Not implemented yet")

    async def test_unauthenticated_returns_401(self):
        """[EC] No Bearer token -> 401."""
        pytest.skip("Not implemented yet")
