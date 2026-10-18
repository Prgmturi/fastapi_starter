from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from fastapi_starter.core.auth import CurrentUser, OAuthProvider
from fastapi_starter.core.auth.cookies import (
    clear_refresh_cookie,
    read_refresh_cookie,
    set_refresh_cookie,
)
from fastapi_starter.core.auth.origin import require_allowed_origin
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.exceptions import (
    ExternalServiceError,
    UnauthorizedError,
    ValidationError,
)
from fastapi_starter.core.logging import get_logger
from fastapi_starter.features.auth.schemas import (
    AccessTokenResponse,
    AuthUrlResponse,
    MessageResponse,
    TokenRequest,
    UserResponse,
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)


def get_oauth_provider(request: Request) -> OAuthProvider:
    """Get OAuthProvider from app state."""
    provider: OAuthProvider = request.app.state.oauth_provider
    return provider


def get_keycloak_settings(request: Request) -> KeycloakSettings:
    """Get KeycloakSettings from app state."""
    settings: KeycloakSettings = request.app.state.settings.keycloak
    return settings


def check_redirect_uri(redirect_uri: str, settings: KeycloakSettings) -> None:
    """Refuse a redirect_uri missing from KEYCLOAK_ALLOWED_REDIRECT_URIS.

    Keycloak sends the authorization code to redirect_uri: a login link
    with another address would send the user's code to whoever made it.
    Keycloak checks its own list too, but a pattern there such as
    http://localhost:* lets any port through. The match is exact, as
    RFC 9700 asks. With an empty list only Keycloak checks.

    Raises:
        ValidationError: If the list is set and redirect_uri is not in it (422).
    """
    allowed = settings.allowed_redirect_uris
    if allowed and redirect_uri not in allowed:
        raise ValidationError("redirect_uri not allowed", field="redirect_uri")


def no_store(response: Response) -> None:
    """Keep the token out of browser and proxy caches (RFC 6749, 5.1)."""
    response.headers["Cache-Control"] = "no-store"


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
    keycloak_settings: Annotated[KeycloakSettings, Depends(get_keycloak_settings)],
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
    check_redirect_uri(redirect_uri, keycloak_settings)

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
    dependencies=[Depends(no_store)],
    summary="Exchange code for tokens",
    description=(
        "Exchange authorization code for tokens. "
        "The refresh token is delivered exclusively via HttpOnly cookie — "
        "it is NOT included in the response body."
    ),
)
async def exchange_token(
    request: TokenRequest,
    response: Response,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
    keycloak_settings: Annotated[KeycloakSettings, Depends(get_keycloak_settings)],
) -> AccessTokenResponse:
    """
    Exchange authorization code for tokens.

    Client sends:
    - code: from provider callback
    - code_verifier: original verifier (not the challenge)
    - redirect_uri: same as used in /login

    Returns access_token in body. Refresh token is set as HttpOnly cookie.
    """
    check_redirect_uri(request.redirect_uri, keycloak_settings)

    tokens = await oauth_provider.exchange_code(
        code=request.code,
        code_verifier=request.code_verifier,
        redirect_uri=request.redirect_uri,
    )

    set_refresh_cookie(
        response=response,
        refresh_token=tokens.refresh_token,
        refresh_expires_in=tokens.refresh_expires_in,
        settings=keycloak_settings,
    )

    return AccessTokenResponse(
        access_token=tokens.access_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@auth_router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_allowed_origin), Depends(no_store)],
    summary="Refresh access token",
    description=(
        "Get new tokens using the refresh token stored in the HttpOnly cookie. "
        "No body required. The rotated refresh token is re-set in the cookie."
    ),
)
async def refresh_token(
    request: Request,
    response: Response,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
    keycloak_settings: Annotated[KeycloakSettings, Depends(get_keycloak_settings)],
) -> AccessTokenResponse:
    """
    Refresh access token.

    Reads the refresh token from the HttpOnly cookie (no body needed).
    With rotation enabled:
    - Returns NEW access_token in body
    - Sets NEW refresh_token cookie (old one is invalidated by Keycloak)
    """
    current_refresh_token = read_refresh_cookie(request, keycloak_settings)

    tokens = await oauth_provider.refresh_token(current_refresh_token)

    set_refresh_cookie(
        response=response,
        refresh_token=tokens.refresh_token,
        refresh_expires_in=tokens.refresh_expires_in,
        settings=keycloak_settings,
    )

    return AccessTokenResponse(
        access_token=tokens.access_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
    )


@auth_router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_allowed_origin)],
    summary="Logout user",
    description="Revoke refresh token and clear the HttpOnly cookie.",
)
async def logout(
    request: Request,
    response: Response,
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
    keycloak_settings: Annotated[KeycloakSettings, Depends(get_keycloak_settings)],
) -> MessageResponse:
    """
    Logout user.

    Reads refresh token from HttpOnly cookie, attempts to revoke it with
    Keycloak, then always clears the cookie. Keycloak revocation failures
    are logged but do not propagate: the client must always end up in a
    clean state regardless of provider availability.
    """
    # UnauthorizedError (missing cookie) propagates normally — no cookie to clear.
    current_refresh_token = read_refresh_cookie(request, keycloak_settings)

    try:
        await oauth_provider.logout(current_refresh_token)
    except (ExternalServiceError, UnauthorizedError) as exc:
        # The two errors OAuthProvider promises. Revocation failure must not
        # prevent cookie clearance: the session is already inaccessible to
        # the client once the cookie is gone.
        logger.warning("logout_revocation_failed", exc_info=exc)

    clear_refresh_cookie(response, keycloak_settings)
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
