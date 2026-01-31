from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fastapi_starter.core.auth.jwks import JWKSManager
from fastapi_starter.core.auth.service import AuthService
from fastapi_starter.core.config import get_settings
from fastapi_starter.core.database import DatabaseManager
from fastapi_starter.core.exceptions import AppExceptionError
from fastapi_starter.core.logging import (
    LoggingMiddleware,
    configure_logging,
    get_logger,
)
from fastapi_starter.features.auth.router import auth_router
from fastapi_starter.features.health.router import health_router

settings = get_settings()
configure_logging(
    environment=settings.app.environment,
    log_level=settings.app.log_level,
)


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan handler for startup and shutdown events."""
    # Startup
    logger.info(
        "application_started",
        app_name=settings.app.name,
        version=settings.app.version,
        environment=settings.app.environment,
        debug=settings.app.debug,
    )

    # Initialize database connection pool
    db_manager = DatabaseManager(settings.database)
    await db_manager.connect()

    try:
        await db_manager.health_check()
        logger.info("database_connected", url=settings.database.url_safe)
    except Exception:
        logger.exception("database_connection_failed")
        raise

    app.state.db_manager = db_manager

    jwks_manager = JWKSManager(settings.keycloak)
    auth_service = AuthService(settings.keycloak, jwks_manager)
    try:
        await auth_service.initialize()
        logger.info("auth_service_ready", issuer=auth_service.issuer)
    except Exception as e:
        logger.exception("auth_service_init_failed", error=str(e))
        raise

    app.state.auth_service = auth_service

    yield

    # Shutdown
    logger.info("application_stopping")
    await app.state.db_manager.disconnect()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.app.is_development else None,
        redoc_url="/redoc" if settings.app.is_development else None,
        openapi_url="/openapi.json" if settings.app.is_development else None,
    )

    # Middleware: ORDINE IMPORTANTE
    # I middleware sono eseguiti in ordine INVERSO rispetto a come li aggiungi
    # Quindi LoggingMiddleware (aggiunto per ultimo) viene eseguito PER PRIMO

    # 1. CORS (eseguito per ultimo)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=settings.server.cors_allow_credentials,
        allow_methods=settings.server.cors_allow_methods,
        allow_headers=settings.server.cors_allow_headers,
    )

    #  Logging
    app.add_middleware(LoggingMiddleware)

    # Exception handlers
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
            path=request.url.path,  # Esplicito per sicurezza
            method=request.method,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"message": "Internal server error", "details": {}},
        )

    # Include routers
    app.include_router(health_router)
    app.include_router(auth_router)

    # Root endpoint
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        """Root endpoint with API information."""
        return {
            "name": settings.app.name,
            "version": settings.app.version,
            "status": "running",
            "docs": "/docs" if settings.app.is_development else None,
        }

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "fastapi_starter.main:app",
        host=settings.server.host,
        port=settings.server.port,
        timeout_keep_alive=settings.server.timeout_keep_alive,
        reload=settings.app.is_development,
        workers=settings.server.workers if not settings.app.is_development else 1,
    )
