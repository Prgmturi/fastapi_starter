from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from fastapi_starter.bootstrap import (
    CleanupFn,
    register_middleware,
    shutdown_services,
    start_services,
)
from fastapi_starter.core.config import Settings, get_settings
from fastapi_starter.core.logging import configure_logging, get_logger
from fastapi_starter.core.problem_details import PROBLEM_RESPONSES
from fastapi_starter.exception_handlers import register_exception_handlers
from fastapi_starter.features.auth.router import auth_router
from fastapi_starter.features.health.router import health_router
from fastapi_starter.features.notes.api.router import notes_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler for startup and shutdown events.

    start_services() adds every service to ``services`` as soon as it is
    open, and the finally block closes them whatever ends the lifespan: a
    normal shutdown, a service that fails to start, or a cancellation.
    uvicorn cancels the lifespan at yield when Ctrl+C arrives during
    startup, and CancelledError is not an Exception.
    """
    settings: Settings = app.state.settings
    services: list[tuple[str, CleanupFn]] = []
    try:
        await start_services(app.state, settings, services)

        logger.info(
            "application_started",
            app_name=settings.app.name,
            version=settings.app.version,
            environment=settings.app.environment,
            debug=settings.app.debug,
        )
        yield
        logger.info("application_stopping")
    finally:
        await shutdown_services(services)
        logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    uvicorn calls this when the server process starts (``--factory``):
    ``python -m fastapi_starter.serve`` in the image, the uvicorn command
    in development. Importing this module builds nothing and reads no
    configuration.

    Args:
        settings: Configuration for this app. When omitted, it is loaded
            from the environment and ``.env``. Tests pass their own.
    """
    if settings is None:
        settings = get_settings()

    configure_logging(
        environment=settings.app.environment,
        log_level=settings.app.log_level,
        app_name=settings.app.name,
        version=settings.app.version,
    )

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
        # Every route documents its errors as problem details (RFC 9457)
        responses=PROBLEM_RESPONSES,
        docs_url="/docs" if settings.app.is_development else None,
        redoc_url="/redoc" if settings.app.is_development else None,
        openapi_url="/openapi.json" if settings.app.is_development else None,
    )

    # Store settings in app.state so lifespan() and dependencies can read them
    app.state.settings = settings

    register_middleware(app, settings.server)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(notes_router)

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
