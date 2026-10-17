"""Origin check for the endpoints that the refresh cookie authenticates."""

from fastapi import Request

from fastapi_starter.core.config.server import ServerSettings
from fastapi_starter.core.exceptions import ForbiddenError


def require_allowed_origin(request: Request) -> None:
    """Reject a browser request sent by a page outside SERVER_CORS_ORIGINS.

    The browser attaches the refresh cookie by itself, so any page can make
    it POST to an endpoint that uses the cookie. That POST needs no CORS
    preflight: CORS only hides the answer, after the request has done its
    work. SameSite=lax blocks it in recent browsers; this is the second
    line of defence.

    The allowed origins are the CORS ones, "*" included: one list decides
    which frontends may use the API. A request without Origin passes: it
    does not come from a browser page (curl, a mobile app). "null", sent by
    sandboxed pages and some privacy settings, never matches "*".

    Raises:
        ForbiddenError: If Origin is present and not allowed (403).
    """
    origin = request.headers.get("origin")
    if origin is None:
        return

    settings: ServerSettings = request.app.state.settings.server
    allowed = settings.cors_origins
    if origin in allowed or ("*" in allowed and origin != "null"):
        return

    raise ForbiddenError("Origin not allowed")
