from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response, status

from fastapi_starter.core.auth import CurrentUser, OAuthProvider
from fastapi_starter.core.config import get_settings
from fastapi_starter.core.exceptions import UnauthorizedError
from fastapi_starter.features.auth.schemas import (
    AccessTokenResponse,
    AuthUrlResponse,
    MessageResponse,
    TokenRequest,
    UserResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_oauth_provider(request: Request) -> OAuthProvider:
    """Get OAuthProvider from app state."""
    provider: OAuthProvider = request.app.state.oauth_provider
    return provider


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Write the refresh token as an HttpOnly cookie on the response."""
    cfg = get_settings().server
    response.set_cookie(
        key=cfg.auth_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=cfg.auth_cookie_secure,
        samesite=cfg.auth_cookie_samesite,
        max_age=cfg.auth_cookie_max_age,
        path=cfg.auth_cookie_path,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Delete the refresh token cookie."""
    cfg = get_settings().server
    response.delete_cookie(
        key=cfg.auth_cookie_name,
        path=cfg.auth_cookie_path,
        samesite=cfg.auth_cookie_samesite,
        secure=cfg.auth_cookie_secure,
    )


@auth_router.get(
    "/login",
    response_model=AuthUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authorization URL",
    description="Returns authorization URL. Client redirects user here.",
)
async def get_login_url(
    redirect_uri: Annotated[
        str,
        Query(description="URI where the provider redirects after login"),
    ],
    code_challenge: Annotated[
        str,
        Query(description="PKCE code challenge (base64url SHA256 of verifier)"),
    ],
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
    state: Annotated[
        str | None,
        Query(description="Optional state for CSRF protection"),
    ] = None,
) -> AuthUrlResponse:
    """
    Get authorization URL for OAuth login.

    Client flow:
    1. Generate code_verifier (random 43-128 chars)
    2. Calculate code_challenge = base64url(sha256(code_verifier))
    3. Call this endpoint with code_challenge
    4. Redirect user to returned authorization_url
    5. After login, provider redirects to redirect_uri with code
    """
    authorization_url = oauth_provider.build_authorization_url(
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
    )

    return AuthUrlResponse(authorization_url=authorization_url)


@auth_router.post(
    "/token",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange code for tokens",
    description="Exchange authorization code for tokens. refresh_token is returned as HttpOnly cookie.",
)
async def exchange_token(
    token_request: TokenRequest,
    response: Response,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
) -> AccessTokenResponse:
    """
    Exchange authorization code for tokens.

    Client sends code + code_verifier + redirect_uri in the JSON body.
    Returns access_token in the JSON body; refresh_token is set as HttpOnly cookie.
    Invalid/expired codes raise UnauthorizedError (propagated from KeycloakClient).
    """
    tokens = await oauth_provider.exchange_code(
        code=token_request.code,
        code_verifier=token_request.code_verifier,
        redirect_uri=token_request.redirect_uri,
    )
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessTokenResponse(
        access_token=tokens.access_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@auth_router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Get new tokens using the refresh_token HttpOnly cookie.",
)
async def refresh_token(
    response: Response,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
    refresh_token: Annotated[
        str | None,
        Cookie(alias="refresh_token", description="HttpOnly refresh token cookie"),
    ] = None,
) -> AccessTokenResponse:
    """
    Refresh access token.

    Reads refresh_token from the HttpOnly cookie set by /token or a previous /refresh.
    With rotation enabled, the old refresh_token is invalidated and a new one is set.
    Cookie missing → 401 (no session to restore).
    Invalid/expired cookie → UnauthorizedError (propagated from KeycloakClient).
    """
    if not refresh_token:
        raise UnauthorizedError("Refresh token cookie missing")

    tokens = await oauth_provider.refresh_token(refresh_token)
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessTokenResponse(
        access_token=tokens.access_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@auth_router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout user",
    description="Revoke refresh token cookie and end session.",
)
async def logout(
    response: Response,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
    refresh_token: Annotated[
        str | None,
        Cookie(alias="refresh_token", description="HttpOnly refresh token cookie"),
    ] = None,
) -> MessageResponse:
    """
    Logout user.

    Reads refresh_token from the HttpOnly cookie, revokes it with Keycloak,
    then clears the cookie. If the cookie is missing (already logged out),
    the cookie is cleared and success is returned — idempotent by design.
    """
    if refresh_token:
        await oauth_provider.logout(refresh_token)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out successfully")


@auth_router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user",
    description="Get authenticated user information.",
)
async def get_me(user: CurrentUser) -> UserResponse:
    """
    Get current user info.

    Requires valid access token in Authorization header.
    """
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        email_verified=user.email_verified,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        roles=[r.value for r in user.roles],
    )
