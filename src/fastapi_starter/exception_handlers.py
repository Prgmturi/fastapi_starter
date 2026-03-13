"""Global exception handlers for the FastAPI application."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from fastapi_starter.core.exceptions import AppExceptionError
from fastapi_starter.core.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers."""

    @app.exception_handler(AppExceptionError)
    async def app_exception_handler(
        request: Request,
        exc: AppExceptionError,
    ) -> JSONResponse:
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
        headers = getattr(exc, "headers", None)

        return JSONResponse(
            status_code=exc.status_code,
            content={"message": exc.message, "details": exc.details},
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle any unhandled exception."""
        if isinstance(exc, HTTPException):
            raise exc

        logger.error(
            "unhandled_exception",
            error_type=type(exc).__name__,
            error_message=str(exc),
            path=request.url.path,
            method=request.method,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"message": "Internal server error", "details": {}},
        )
