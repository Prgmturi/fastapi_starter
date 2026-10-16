"""Global exception handlers: every error leaves as an RFC 9457 problem."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi_starter.core.exceptions import AppExceptionError
from fastapi_starter.core.logging import get_logger
from fastapi_starter.core.problem_details import (
    INTERNAL_ERROR_DETAIL,
    problem_response,
)

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers."""

    @app.exception_handler(AppExceptionError)
    async def app_exception_handler(
        request: Request,
        exc: AppExceptionError,
    ) -> Response:
        """Handle application-specific exceptions."""
        logger.warning(
            "app_exception",
            error_type=type(exc).__name__,
            message=exc.message,
            details=exc.details,
            status_code=exc.status_code,
            path=request.url.path,
            method=request.method,
        )
        return problem_response(
            exc.status_code,
            exc.message,
            headers=getattr(exc, "headers", None),
            extensions=exc.details,
        )

    # Starlette's class, which FastAPI's HTTPException extends: routing
    # raises it for unknown paths (404) and wrong methods (405).
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> Response:
        """Handle HTTPException, from routing or from route code."""
        if not is_body_allowed_for_status_code(exc.status_code):
            return Response(status_code=exc.status_code, headers=exc.headers)

        # Only text becomes the detail: str() of a dict or an enum would show
        # Python reprs. Structured data goes in an AppExceptionError subclass,
        # whose details become members of the problem.
        detail = exc.detail if isinstance(exc.detail, str) else None
        return problem_response(exc.status_code, detail, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> Response:
        """Handle invalid query, path, header or body values (422)."""
        # loc, msg and type tell the client what to fix. The rejected value
        # ("input") stays out: a password that is too short would come back
        # in the response.
        errors = [
            {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return problem_response(
            422, "Request validation failed", extensions={"errors": errors}
        )

    # Last resort. Exceptions from the routes are answered by
    # UnhandledExceptionMiddleware, whose 500 keeps the CORS, security and
    # X-Request-ID headers. Starlette runs this handler outside every
    # middleware, so it only gets what a middleware raises, and its 500 has
    # none of those headers.
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> Response:
        """Handle an exception raised outside UnhandledExceptionMiddleware."""
        logger.error(
            "unhandled_exception",
            error_type=type(exc).__name__,
            error_message=str(exc),
            path=request.url.path,
            method=request.method,
            exc_info=True,
        )
        return problem_response(500, INTERNAL_ERROR_DETAIL)
