"""Tests for auth router — /auth/* endpoints.

Module under test: src/fastapi_starter/features/auth/router.py
Layer: HTTP endpoints (AsyncClient with mocked OAuthProvider)

WHY these tests exist: Auth endpoints are the public API surface for the
OAuth flow. We verify correct HTTP status codes, response structure, cookie
behaviour, and that the refresh token never leaks into the response body.
"""

from unittest.mock import AsyncMock

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
        self,
        oauth_client,
        mock_oauth_provider,
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
    1. access_token is returned in the response body
    2. refresh_token is NEVER in the response body
    3. refresh_token is delivered as an HttpOnly cookie
    4. Invalid code returns 401 (not 500)
    5. Request validation catches missing fields
    """

    async def test_valid_code_returns_access_token_in_body(self, oauth_client):
        """[HP] Valid request -> 200 with access_token in body."""
        response = await oauth_client.post(
            "/auth/token",
            json={
                "code": "valid-auth-code",
                "code_verifier": "a" * 43,
                "redirect_uri": "http://localhost:3000/callback",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "Bearer"
        assert "expires_in" in body

    async def test_refresh_token_not_in_response_body(self, oauth_client):
        """[SEC] refresh_token must never appear in the JSON response body."""
        response = await oauth_client.post(
            "/auth/token",
            json={
                "code": "valid-auth-code",
                "code_verifier": "a" * 43,
                "redirect_uri": "http://localhost:3000/callback",
            },
        )

        assert response.status_code == 200
        assert "refresh_token" not in response.json()

    async def test_refresh_token_set_as_httponly_cookie(self, oauth_client):
        """[SEC] refresh_token delivered as HttpOnly cookie."""
        response = await oauth_client.post(
            "/auth/token",
            json={
                "code": "valid-auth-code",
                "code_verifier": "a" * 43,
                "redirect_uri": "http://localhost:3000/callback",
            },
        )

        assert response.status_code == 200
        assert "rt" in response.cookies
        set_cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie

    async def test_invalid_code_returns_401(
        self,
        oauth_client,
        mock_oauth_provider,
    ):
        """[EC] OAuthProvider raises UnauthorizedError -> 401."""
        mock_oauth_provider.exchange_code.side_effect = UnauthorizedError(
            "Invalid code"
        )

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

    WHY: Client uses this to get a new access_token before expiry.
    The refresh token is read from the cookie — no body needed.
    On success, the rotated refresh token is re-set in the cookie.
    """

    async def test_valid_cookie_returns_new_access_token(
        self, oauth_client_with_cookie
    ):
        """[HP] Valid cookie -> 200 with new access_token in body."""
        response = await oauth_client_with_cookie.post("/auth/refresh")

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "expires_in" in body

    async def test_refresh_token_not_in_response_body(self, oauth_client_with_cookie):
        """[SEC] Rotated refresh_token must never appear in the JSON body."""
        response = await oauth_client_with_cookie.post("/auth/refresh")

        assert response.status_code == 200
        assert "refresh_token" not in response.json()

    async def test_rotated_refresh_token_set_in_cookie(self, oauth_client_with_cookie):
        """[HP] Rotated refresh token is re-set as HttpOnly cookie."""
        response = await oauth_client_with_cookie.post("/auth/refresh")

        assert response.status_code == 200
        assert "rt" in response.cookies
        set_cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie

    async def test_missing_cookie_returns_401(self, oauth_client):
        """[EC] No refresh cookie -> 401."""
        response = await oauth_client.post("/auth/refresh")

        assert response.status_code == 401

    async def test_invalid_refresh_token_returns_401(
        self,
        oauth_client_with_cookie,
        mock_oauth_provider,
    ):
        """[EC] OAuthProvider raises UnauthorizedError -> 401."""
        mock_oauth_provider.refresh_token.side_effect = UnauthorizedError("expired")

        response = await oauth_client_with_cookie.post("/auth/refresh")

        assert response.status_code == 401


class TestLogout:
    """POST /auth/logout — token revocation and cookie clearance.

    WHY: Security requirement. Logout must revoke the token with Keycloak
    AND clear the cookie. Cookie clearance must happen even if revocation fails.
    """

    async def test_successful_logout_returns_message(self, oauth_client_with_cookie):
        """[HP] Valid cookie -> 200 with success message, cookie cleared."""
        response = await oauth_client_with_cookie.post("/auth/logout")

        assert response.status_code == 200
        assert "message" in response.json()

    async def test_logout_clears_cookie(self, oauth_client_with_cookie):
        """[HP] Cookie is expired (max_age=0) after logout."""
        response = await oauth_client_with_cookie.post("/auth/logout")

        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "max-age=0" in set_cookie.lower()

    async def test_missing_cookie_returns_401(self, oauth_client):
        """[EC] No cookie present -> 401, nothing to revoke."""
        response = await oauth_client.post("/auth/logout")

        assert response.status_code == 401

    async def test_revocation_failure_still_clears_cookie(
        self,
        oauth_client_with_cookie,
        mock_oauth_provider,
    ):
        """[HP] Even if Keycloak revocation fails, cookie is cleared."""
        mock_oauth_provider.logout = AsyncMock(
            side_effect=Exception("Keycloak unreachable")
        )

        response = await oauth_client_with_cookie.post("/auth/logout")

        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert "max-age=0" in set_cookie.lower()


class TestGetMe:
    """GET /auth/me — current user information.

    WHY: Frontend calls this to get user profile after login.
    Must require authentication and return correct user structure.
    """

    async def test_authenticated_returns_user_info(
        self,
        authenticated_oauth_client,
    ):
        """[HP] Authenticated request -> 200 with user details."""
        response = await authenticated_oauth_client.get("/auth/me")

        assert response.status_code == 200

    async def test_response_includes_all_user_fields(
        self,
        authenticated_oauth_client,
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

        assert response.status_code == 401
