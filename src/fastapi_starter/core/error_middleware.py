"""Unexpected exceptions become a 500 inside the middleware stack."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fastapi_starter.core.logging import get_logger
from fastapi_starter.core.problem_details import (
    INTERNAL_ERROR_DETAIL,
    problem_response,
)

logger = get_logger(__name__)


class UnhandledExceptionMiddleware:
    """Answer 500 to an exception that no exception handler took.

    Starlette runs a handler for ``Exception`` in ServerErrorMiddleware, which
    wraps every other middleware: its 500 left without CORS, security headers
    and X-Request-ID. This middleware is registered first, so it is the one
    closest to the routes, and every other middleware handles its 500 like
    any other response.

    Pure ASGI rather than BaseHTTPMiddleware: it must see the exception where
    it is raised and know whether the response has already started.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_and_track(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_and_track)
        except Exception as exc:
            # Part of the response has already left: it cannot be replaced.
            # The handler for Exception logs it, then the server closes the
            # connection.
            if response_started:
                raise

            logger.error(
                "unhandled_exception",
                error_type=type(exc).__name__,
                error_message=str(exc),
                path=scope["path"],
                method=scope["method"],
                exc_info=True,
            )
            response = problem_response(500, INTERNAL_ERROR_DETAIL)
            await response(scope, receive, send)
