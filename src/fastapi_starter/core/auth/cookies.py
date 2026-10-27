"""HttpOnly cookie management for the refresh token.

Security invariants enforced here:
- httponly=True always (no JS access)
- secure follows settings (must be True in production)
- samesite follows settings, "lax" by default: prevents CSRF on cross-site
  requests while allowing the OAuth redirects
- path follows settings, "/" by default, because the '__Host-' prefix
  requires it: the browser sends the cookie to every path of the API, not
  only to /auth
- max_age derived from the actual Keycloak refresh_expires_in (0 → session cookie)
- The '__Host-' prefix in the default name enforces Secure + Path=/ at browser level;
  AuthCookieSettings refuses a '__Host-' name without them, so in development over
  plain http the name must not carry the prefix.
"""

from fastapi import Request, Response

from fastapi_starter.core.config.auth_cookie import AuthCookieSettings
from fastapi_starter.core.exceptions import UnauthorizedError
from fastapi_starter.core.logging import get_logger

logger = get_logger(__name__)


def set_refresh_cookie(
    response: Response,
    refresh_token: str,
    refresh_expires_in: int,
    settings: AuthCookieSettings,
) -> None:
    """Attach the refresh token as an HttpOnly cookie to *response*.

    Args:
        response: FastAPI/Starlette response to mutate.
        refresh_token: Opaque refresh token string from Keycloak.
        refresh_expires_in: Token lifetime in seconds (0 = session cookie).
        settings: The cookie's name, Secure flag, SameSite and path.
    """
    # max_age=None produces a session cookie (no Expires header).
    max_age: int | None = refresh_expires_in if refresh_expires_in > 0 else None

    response.set_cookie(
        key=settings.name,
        value=refresh_token,
        httponly=True,
        secure=settings.secure,
        samesite=settings.samesite,
        path=settings.path,
        max_age=max_age,
        # domain intentionally omitted: let browser infer it from the request host.
        # With '__Host-' prefix the browser also rejects a Domain attribute.
    )

    logger.debug(
        "refresh_cookie_set",
        cookie_name=settings.name,
        path=settings.path,
        max_age=max_age,
        secure=settings.secure,
        samesite=settings.samesite,
    )


def clear_refresh_cookie(response: Response, settings: AuthCookieSettings) -> None:
    """Expire the refresh token cookie immediately.

    Sets max_age=0 and an empty value so all browsers (including those that
    ignore max_age=0) receive an explicit expiration.
    """
    response.set_cookie(
        key=settings.name,
        value="",
        httponly=True,
        secure=settings.secure,
        samesite=settings.samesite,
        path=settings.path,
        max_age=0,
    )

    logger.debug("refresh_cookie_cleared", cookie_name=settings.name)


def read_refresh_cookie(request: Request, settings: AuthCookieSettings) -> str:
    """Extract the refresh token from the HttpOnly cookie.

    Args:
        request: Incoming FastAPI request.
        settings: The cookie settings, for its name.

    Returns:
        The refresh token string.

    Raises:
        UnauthorizedError: If the cookie is absent or empty.
    """
    token = request.cookies.get(settings.name)

    if not token:
        logger.warning("refresh_cookie_missing", cookie_name=settings.name)
        raise UnauthorizedError("Refresh token cookie missing or expired")

    return token
