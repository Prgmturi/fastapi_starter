from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from fastapi_starter.core.config import get_settings
from fastapi_starter.core.logging import configure_logging, get_logger
from fastapi_starter.exception_handlers import register_exception_handlers
from fastapi_starter.features.auth.router import auth_router
from fastapi_starter.features.health.router import health_router
from fastapi_starter.setup import (
    CleanupFn,
    init_auth_service,
    init_database,
    init_oauth_provider,
    register_middleware,
    shutdown_services,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler for startup and shutdown events."""
    settings = get_settings()
    logger.info(
        "application_started",
        app_name=settings.app.name,
        version=settings.app.version,
        environment=settings.app.environment,
        debug=settings.app.debug,
    )

    services: list[tuple[str, CleanupFn]] = []
    try:
        db_manager = await init_database(app.state)
        services.append(("database", db_manager.disconnect))

        jwks_manager = await init_auth_service(app.state)
        services.append(("jwks_manager", jwks_manager.close))

        keycloak_client = await init_oauth_provider(app.state)
        services.append(("oauth_provider", keycloak_client.close))
    except Exception:
        await shutdown_services(services)
        raise

    yield

    logger.info("application_stopping")
    await shutdown_services(services)
    logger.info("application_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(
        environment=settings.app.environment,
        log_level=settings.app.log_level,
    )

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        debug=settings.app.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.app.is_development else None,
        redoc_url="/redoc" if settings.app.is_development else None,
        openapi_url="/openapi.json" if settings.app.is_development else None,
    )

    register_middleware(app)
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


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "fastapi_starter.main:app",
        host=settings.server.host,
        port=settings.server.port,
        timeout_keep_alive=settings.server.timeout_keep_alive,
        reload=settings.app.is_development,
        workers=settings.server.workers if not settings.app.is_development else 1,
    )
