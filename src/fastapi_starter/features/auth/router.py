from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from fastapi_starter.core.auth import CurrentUser, OAuthProvider
from fastapi_starter.features.auth.schemas import (
    AuthUrlResponse,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    TokenRequest,
    TokenResponse,
    UserResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_oauth_provider(request: Request) -> OAuthProvider:
    """Get OAuthProvider from app state."""
    provider: OAuthProvider = request.app.state.oauth_provider
    return provider


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
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange code for tokens",
    description="Exchange authorization code for access and refresh tokens.",
)
async def exchange_token(
    request: TokenRequest,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
) -> TokenResponse:
    """
    Exchange authorization code for tokens.

    Client sends:
    - code: from provider callback
    - code_verifier: original verifier (not the challenge)
    - redirect_uri: same as used in /login

    Returns access_token and refresh_token.
    """
    return await oauth_provider.exchange_code(
        code=request.code,
        code_verifier=request.code_verifier,
        redirect_uri=request.redirect_uri,
    )


@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Get new tokens using refresh token.",
)
async def refresh_token(
    request: RefreshRequest,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
) -> TokenResponse:
    """
    Refresh access token.

    With rotation enabled:
    - Returns NEW access_token AND NEW refresh_token
    - Old refresh_token becomes invalid
    """
    return await oauth_provider.refresh_token(request.refresh_token)


@auth_router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout user",
    description="Revoke refresh token and end session.",
)
async def logout(
    request: LogoutRequest,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
) -> MessageResponse:
    """
    Logout user.

    Revokes refresh token with the auth provider.
    Client should also clear local tokens.
    """
    await oauth_provider.logout(request.refresh_token)
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
