from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI

from fastapi_starter.core.config import Settings, get_settings
from fastapi_starter.core.logging import configure_logging, get_logger
from fastapi_starter.core.problem_details import PROBLEM_RESPONSES
from fastapi_starter.exception_handlers import register_exception_handlers
from fastapi_starter.features.auth.router import auth_router
from fastapi_starter.features.health.router import health_router
from fastapi_starter.setup import (
    CleanupFn,
    create_keycloak_http_client,
    init_auth_service,
    init_database,
    init_oauth_provider,
    register_middleware,
    shutdown_services,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler for startup and shutdown events.

    Every service is added to ``services`` as soon as it is open, and the
    finally block closes them whatever ends the lifespan: a normal
    shutdown, a service that fails to start, or a cancellation. uvicorn
    cancels the lifespan at yield when Ctrl+C arrives during startup, and
    CancelledError is not an Exception.
    """
    settings: Settings = app.state.settings
    services: list[tuple[str, CleanupFn]] = []
    try:
        db_manager = await init_database(app.state, settings.database)
        services.append(("database", db_manager.disconnect))

        # One client for every call to Keycloak: signing keys and tokens.
        # It is registered before the adapters that use it, so a failure
        # while they start still closes it.
        keycloak_http = create_keycloak_http_client(settings.keycloak)
        services.append(("keycloak_http_client", keycloak_http.aclose))

        await init_auth_service(app.state, settings.keycloak, keycloak_http)
        await init_oauth_provider(app.state, settings.keycloak, keycloak_http)

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

    uvicorn calls this when the server process starts (``--factory``).
    Importing this module builds nothing and reads no configuration.

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


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "fastapi_starter.main:create_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        timeout_keep_alive=settings.server.timeout_keep_alive,
        reload=settings.app.is_development,
        workers=settings.server.workers if not settings.app.is_development else 1,
    )
