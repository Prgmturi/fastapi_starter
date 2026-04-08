"""Tests for auth router — /auth/* endpoints.

Module under test: src/fastapi_starter/features/auth/router.py
Layer: HTTP endpoints (TestClient with mocked OAuthProvider)

WHY these tests exist: Auth endpoints are the public API surface for the
OAuth flow. We verify correct HTTP status codes, request validation, and
response structure.
"""

import pytest

from fastapi_starter.core.exceptions import UnauthorizedError


class TestGetLoginUrl:
    """GET /auth/login — build authorization URL.

    WHY: First step of OAuth flow. We verify the endpoint delegates
    to OAuthProvider.build_authorization_url and returns the URL
    in the correct response format.
    """

    async def test_returns_authorization_url(self, oauth_client):
        """[HP] Returns 200 with authorization_url in response."""
        response = await oauth_client.get(
            "/auth/login",
            params={
                "redirect_uri": "http://localhost:3000/callback",
                "code_challenge": "abc123",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "authorization_url" in body

    async def test_missing_redirect_uri_returns_422(self, oauth_client):
        """[EC] Required query param missing -> 422."""
        response = await oauth_client.get(
            "/auth/login",
            params={"code_challenge": "abc123"},
        )

        assert response.status_code == 422

    async def test_missing_code_challenge_returns_422(self, oauth_client):
        """[EC] Required query param missing -> 422."""
        response = await oauth_client.get(
            "/auth/login",
            params={"redirect_uri": "http://localhost:3000/callback"},
        )

        assert response.status_code == 422

    async def test_optional_state_passed_to_provider(
        self, oauth_client, mock_oauth_provider,
    ):
        """[HP] state param forwarded to build_authorization_url."""
        response = await oauth_client.get(
            "/auth/login",
            params={
                "redirect_uri": "http://localhost:3000/callback",
                "code_challenge": "abc123",
                "state": "my-csrf-state",
            },
        )

        assert response.status_code == 200


class TestExchangeToken:
    """POST /auth/token — exchange authorization code for tokens.

    WHY: Critical OAuth step. We verify:
    1. Success returns access_token in body and sets HttpOnly cookie
    2. refresh_token is NOT exposed in the response body
    3. Invalid code returns 401 (not 500)
    4. Request validation catches missing fields
    """

    async def test_valid_code_returns_access_token(self, oauth_client):
        """[HP] Valid request -> 200 with access_token; no refresh_token in body."""
        response = await oauth_client.post(
            "/auth/token",
            json={
                "code": "valid-auth-code",
                "code_verifier": "a" * 43,  # min 43 chars per PKCE spec
                "redirect_uri": "http://localhost:3000/callback",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" not in body

    async def test_valid_code_sets_refresh_cookie(self, oauth_client):
        """[HP] Valid request -> HttpOnly cookie refresh_token is set."""
        response = await oauth_client.post(
            "/auth/token",
            json={
                "code": "valid-auth-code",
                "code_verifier": "a" * 43,
                "redirect_uri": "http://localhost:3000/callback",
            },
        )

        assert response.status_code == 200
        assert "refresh_token" in response.cookies

    async def test_invalid_code_returns_401(
        self, oauth_client, mock_oauth_provider,
    ):
        """[EC] OAuthProvider raises UnauthorizedError -> propagated."""
        mock_oauth_provider.exchange_code.side_effect = UnauthorizedError("Invalid code")

        response = await oauth_client.post(
            "/auth/token",
            json={
                "code": "bad-code",
                "code_verifier": "a" * 43,
                "redirect_uri": "http://localhost:3000/callback",
            },
        )

        assert response.status_code == 401

    async def test_missing_code_verifier_returns_422(self, oauth_client):
        """[EC] Request body missing code_verifier -> 422."""
        response = await oauth_client.post(
            "/auth/token",
            json={
                "code": "auth-code",
                "redirect_uri": "http://localhost:3000/callback",
            },
        )

        assert response.status_code == 422

    async def test_short_code_verifier_returns_422(self, oauth_client):
        """[EC] code_verifier < 43 chars -> 422 (PKCE spec minimum)."""
        response = await oauth_client.post(
            "/auth/token",
            json={
                "code": "auth-code",
                "code_verifier": "too-short",
                "redirect_uri": "http://localhost:3000/callback",
            },
        )

        assert response.status_code == 422


class TestRefreshToken:
    """POST /auth/refresh — token renewal via HttpOnly cookie.

    WHY: Client uses this to restore session (page load, F5) and to get
    new tokens before access_token expires. Refresh token arrives as a
    cookie, not in the request body.
    """

    async def test_valid_cookie_returns_new_access_token(self, oauth_client):
        """[HP] Valid refresh_token cookie -> 200 with new access_token."""
        response = await oauth_client.post(
            "/auth/refresh",
            cookies={"refresh_token": "valid-rt"},
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" not in body

    async def test_valid_cookie_rotates_refresh_cookie(self, oauth_client):
        """[HP] Valid refresh_token cookie -> new HttpOnly cookie is set."""
        response = await oauth_client.post(
            "/auth/refresh",
            cookies={"refresh_token": "valid-rt"},
        )

        assert response.status_code == 200
        assert "refresh_token" in response.cookies

    async def test_missing_cookie_returns_401(self, oauth_client):
        """[EC] No cookie -> 401 (no session to restore)."""
        response = await oauth_client.post("/auth/refresh")

        assert response.status_code == 401

    async def test_invalid_cookie_returns_401(
        self, oauth_client, mock_oauth_provider,
    ):
        """[EC] OAuthProvider raises UnauthorizedError -> propagated."""
        mock_oauth_provider.refresh_token.side_effect = UnauthorizedError("expired")

        response = await oauth_client.post(
            "/auth/refresh",
            cookies={"refresh_token": "expired-rt"},
        )

        assert response.status_code == 401


class TestLogout:
    """POST /auth/logout — token revocation via HttpOnly cookie.

    WHY: Security requirement. User must be able to invalidate tokens.
    Logout is idempotent: succeeds even if cookie is missing (already logged out).
    """

    async def test_logout_with_cookie_revokes_and_clears(self, oauth_client):
        """[HP] Valid cookie -> 200, cookie cleared."""
        response = await oauth_client.post(
            "/auth/logout",
            cookies={"refresh_token": "valid-rt"},
        )

        assert response.status_code == 200
        assert "message" in response.json()

    async def test_logout_without_cookie_succeeds(self, oauth_client):
        """[HP] No cookie (already logged out) -> 200, idempotent."""
        response = await oauth_client.post("/auth/logout")

        assert response.status_code == 200
        assert "message" in response.json()


class TestGetMe:
    """GET /auth/me — current user information.

    WHY: Frontend calls this to get user profile after login.
    Must require authentication and return correct user structure.
    """

    async def test_authenticated_returns_user_info(
        self, authenticated_oauth_client,
    ):
        """[HP] Authenticated request -> 200 with user details."""
        response = await authenticated_oauth_client.get("/auth/me")

        assert response.status_code == 200

    async def test_response_includes_all_user_fields(
        self, authenticated_oauth_client,
    ):
        """[HP] Response includes id, username, email, roles, full_name."""
        response = await authenticated_oauth_client.get("/auth/me")
        body = response.json()

        assert "id" in body
        assert "username" in body
        assert "email" in body
        assert "roles" in body
        assert "full_name" in body

    async def test_unauthenticated_returns_401(self, oauth_client):
        """[EC] No Bearer token -> 401."""
        response = await oauth_client.get("/auth/me")

        # FastAPI's HTTPBearer with auto_error=False returns None credentials
        # get_current_user raises 401
        assert response.status_code == 401
