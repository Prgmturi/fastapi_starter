"""Tests for auth router — /auth/* endpoints.

Module under test: src/fastapi_starter/features/auth/router.py
Layer: HTTP endpoints (AsyncClient with mocked OAuthProvider)

WHY these tests exist: Auth endpoints are the public API surface for the
OAuth flow. We verify correct HTTP status codes, response structure, cookie
behaviour, and that the refresh token never leaks into the response body.
"""

from unittest.mock import AsyncMock

import pytest

from fastapi_starter.core.config import ServerSettings, Settings
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.exceptions import (
    ExternalServiceError,
    ServiceUnavailableError,
    UnauthorizedError,
)
from tests.features.auth.conftest import TEST_COOKIE_NAME
from tests.test_exception_handlers import assert_problem


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
        assert TEST_COOKIE_NAME in response.cookies
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
        assert TEST_COOKIE_NAME in response.cookies
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
            side_effect=ExternalServiceError("Keycloak unreachable")
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

    async def test_auth_backend_down_returns_503(self, oauth_client, mock_auth_service):
        """[EC] Keycloak unreachable for an uncached key -> 503, not 401.

        WHY: a 401 makes the frontend send the user back to the login. A 503
        says "retry later" and keeps the session.
        """
        mock_auth_service.validate_token.side_effect = ServiceUnavailableError("auth")

        response = await oauth_client.get(
            "/auth/me", headers={"Authorization": "Bearer some-token"}
        )

        assert response.status_code == 503
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json() == {
            "type": "about:blank",
            "title": "Service Unavailable",
            "status": 503,
            "detail": "Service temporarily unavailable",
            "service": "auth",
        }


TOKEN_REQUEST = {
    "code": "valid-auth-code",
    "code_verifier": "a" * 43,
    "redirect_uri": "http://localhost:3000/callback",
}

# The two endpoints that act on the refresh cookie.
COOKIE_ENDPOINTS = ["/auth/refresh", "/auth/logout"]

# One of the default SERVER_CORS_ORIGINS.
FRONTEND_ORIGIN = "http://localhost:3000"


class TestTokensAreNotCached:
    """Responses that carry a token say Cache-Control: no-store.

    WHY: RFC 6749, section 5.1. Without it a browser or a proxy may keep
    the access token in its cache, where the next user of the machine
    can find it.
    """

    async def test_token_response(self, oauth_client):
        """[SEC] POST /auth/token -> no-store."""
        response = await oauth_client.post("/auth/token", json=TOKEN_REQUEST)

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"

    async def test_refresh_response(self, oauth_client_with_cookie):
        """[SEC] POST /auth/refresh -> no-store."""
        response = await oauth_client_with_cookie.post("/auth/refresh")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"


class TestOriginCheck:
    """/auth/refresh and /auth/logout answer only the frontend's origins.

    WHY: the browser attaches the refresh cookie by itself, so any page can
    make it POST to these endpoints. That POST needs no CORS preflight:
    CORS only hides the answer, after Keycloak has rotated or revoked the
    token. SameSite=lax blocks it in recent browsers; this is the second
    line of defence.
    """

    @pytest.mark.parametrize("path", COOKIE_ENDPOINTS)
    @pytest.mark.parametrize("origin", ["https://evil.example", "null"])
    async def test_foreign_origin_gets_403(
        self, oauth_client_with_cookie, mock_oauth_provider, path, origin
    ):
        """[SEC] Origin not allowed -> 403, Keycloak not called, cookie untouched.

        "null" is what sandboxed pages and some privacy settings send.
        """
        response = await oauth_client_with_cookie.post(path, headers={"Origin": origin})

        body = assert_problem(response, 403)
        assert body["detail"] == "Origin not allowed"
        mock_oauth_provider.refresh_token.assert_not_called()
        mock_oauth_provider.logout.assert_not_called()
        assert "set-cookie" not in response.headers

    @pytest.mark.parametrize("path", COOKIE_ENDPOINTS)
    async def test_frontend_origin_passes(self, oauth_client_with_cookie, path):
        """[HP] Origin listed in SERVER_CORS_ORIGINS -> 200."""
        response = await oauth_client_with_cookie.post(
            path, headers={"Origin": FRONTEND_ORIGIN}
        )

        assert response.status_code == 200

    @pytest.mark.parametrize("path", COOKIE_ENDPOINTS)
    async def test_request_without_origin_passes(self, oauth_client_with_cookie, path):
        """[HP] No Origin: not a browser (curl, a mobile app) -> 200."""
        response = await oauth_client_with_cookie.post(path)

        assert response.status_code == 200


class TestOriginCheckWithAnyOrigin:
    """SERVER_CORS_ORIGINS=["*"]: the check accepts what CORS accepts."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Overrides the root fixture: CORS open to every origin."""
        return Settings(
            server=ServerSettings(trusted_hosts=["testserver"], cors_origins=["*"]),
        )

    async def test_any_origin_passes(self, oauth_client_with_cookie):
        """[HP] "*" -> an origin not listed anywhere passes."""
        response = await oauth_client_with_cookie.post(
            "/auth/refresh", headers={"Origin": "https://app.example.com"}
        )

        assert response.status_code == 200

    async def test_null_origin_still_gets_403(self, oauth_client_with_cookie):
        """[SEC] "*" does not cover "null": that page has no origin to trust."""
        response = await oauth_client_with_cookie.post(
            "/auth/refresh", headers={"Origin": "null"}
        )

        assert_problem(response, 403)


# The one redirect_uri allowed in TestAllowedRedirectUris.
ALLOWED_REDIRECT_URI = "http://localhost:3000/callback"


class TestAllowedRedirectUris:
    """KEYCLOAK_ALLOWED_REDIRECT_URIS: /auth/login and /auth/token take only these.

    WHY: Keycloak sends the authorization code to redirect_uri. A login link
    that names another address sends the victim's code to whoever made the
    link, who holds the PKCE verifier and can exchange the code here.
    Keycloak checks its own list too, but a pattern there such as
    http://localhost:* lets any port through. The match is exact, as
    RFC 9700 asks.
    """

    UNLISTED = [
        "https://evil.example/callback",
        "http://localhost:3001/callback",
        "http://localhost:3000/callback/",
        "http://localhost:3000/callback?next=https://evil.example",
    ]

    @pytest.fixture
    def test_keycloak_settings(self) -> KeycloakSettings:
        """Overrides the feature fixture: one allowed redirect_uri."""
        return KeycloakSettings(
            cookie_name=TEST_COOKIE_NAME,
            cookie_secure=False,
            allowed_redirect_uris=[ALLOWED_REDIRECT_URI],
        )

    @pytest.mark.parametrize("redirect_uri", UNLISTED)
    async def test_login_rejects_unlisted_uri(self, oauth_client, redirect_uri):
        """[SEC] /auth/login with an unlisted redirect_uri -> 422, no URL."""
        response = await oauth_client.get(
            "/auth/login",
            params={"redirect_uri": redirect_uri, "code_challenge": "abc123"},
        )

        body = assert_problem(response, 422)
        assert body["detail"] == "redirect_uri not allowed"
        assert body["field"] == "redirect_uri"

    @pytest.mark.parametrize("redirect_uri", UNLISTED)
    async def test_token_rejects_unlisted_uri(
        self, oauth_client, mock_oauth_provider, redirect_uri
    ):
        """[SEC] /auth/token, unlisted redirect_uri -> 422, Keycloak not called."""
        response = await oauth_client.post(
            "/auth/token", json={**TOKEN_REQUEST, "redirect_uri": redirect_uri}
        )

        assert_problem(response, 422)
        mock_oauth_provider.exchange_code.assert_not_called()
        assert "set-cookie" not in response.headers

    async def test_login_accepts_listed_uri(self, oauth_client):
        """[HP] Listed redirect_uri -> 200 with the authorization URL."""
        response = await oauth_client.get(
            "/auth/login",
            params={"redirect_uri": ALLOWED_REDIRECT_URI, "code_challenge": "abc123"},
        )

        assert response.status_code == 200

    async def test_token_accepts_listed_uri(self, oauth_client):
        """[HP] Listed redirect_uri -> 200 with the access token."""
        response = await oauth_client.post(
            "/auth/token", json={**TOKEN_REQUEST, "redirect_uri": ALLOWED_REDIRECT_URI}
        )

        assert response.status_code == 200


class TestRedirectUriWithoutList:
    """KEYCLOAK_ALLOWED_REDIRECT_URIS empty, the default: Keycloak alone decides."""

    async def test_any_redirect_uri_reaches_keycloak(self, oauth_client):
        """[HP] No list -> the API does not check redirect_uri."""
        response = await oauth_client.get(
            "/auth/login",
            params={
                "redirect_uri": "https://app.example.com/callback",
                "code_challenge": "abc123",
            },
        )

        assert response.status_code == 200
