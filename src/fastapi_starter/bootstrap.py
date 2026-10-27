"""Composition root helpers — service initialization and shutdown.

Every adapter goes into app.state through a variable typed as its port
(``provider: OAuthProvider = KeycloakClient(...)``). app.state has no
types and the getters trust what they read, so this assignment is the one
place where mypy checks that an adapter still matches its port.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import State
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fastapi_starter.core.auth.extractors import KeycloakClaimExtractor
from fastapi_starter.core.auth.jwks import JWKSTokenDecoder
from fastapi_starter.core.auth.jwks_manager import JWKSManager
from fastapi_starter.core.auth.protocols import OAuthProvider, TokenValidator
from fastapi_starter.core.auth.service import AuthService
from fastapi_starter.core.body_limit import BodySizeLimitMiddleware
from fastapi_starter.core.config import (
    DatabaseSettings,
    KeycloakSettings,
    ServerSettings,
)
from fastapi_starter.core.database import DatabaseManager, database_url
from fastapi_starter.core.database.protocols import DatabaseProvider
from fastapi_starter.core.error_middleware import UnhandledExceptionMiddleware
from fastapi_starter.core.logging import (
    REQUEST_ID_HEADER,
    LoggingMiddleware,
    get_logger,
)
from fastapi_starter.core.security import SecureHeadersMiddleware
from fastapi_starter.features.auth.client import KeycloakClient
from fastapi_starter.features.health.router import health_router

logger = get_logger(__name__)

CleanupFn = Callable[[], Awaitable[Any]]


async def init_database(
    app_state: State, settings: DatabaseSettings
) -> DatabaseManager:
    """Create connection pool, verify connectivity, register in app state."""
    db_manager = DatabaseManager(settings)
    await db_manager.connect()

    try:
        await db_manager.health_check()
    except Exception:
        logger.exception("database_connection_failed")
        await db_manager.disconnect()
        raise

    logger.info(
        "database_connected",
        url=database_url(settings).render_as_string(hide_password=True),
    )
    # app.state holds the port, for the routes. The lifespan gets the
    # manager itself, because disconnect() is not part of the port.
    provider: DatabaseProvider = db_manager
    app_state.db_manager = provider
    return db_manager


def create_keycloak_http_client(settings: KeycloakSettings) -> httpx.AsyncClient:
    """HTTP client shared by every Keycloak adapter: one connection pool.

    The adapters only use it. Whoever creates it closes it — the lifespan.
    """
    return httpx.AsyncClient(timeout=settings.request_timeout)


async def init_auth_service(
    app_state: State, settings: KeycloakSettings, http_client: httpx.AsyncClient
) -> None:
    """Wire auth adapters to ports, pre-fetch JWKS keys, register in app state."""
    jwks_manager = JWKSManager(settings, http_client)
    issuer = settings.issuer

    decoder = JWKSTokenDecoder(
        key_provider=jwks_manager,
        issuer=issuer,
        allowed_clients=settings.allowed_clients,
        audience=settings.audience or None,
    )
    extractor = KeycloakClaimExtractor(settings.client_id)
    # JWKSTokenDecoder implements both TokenDecoder and HealthCheckable
    # (health_check delegates to the underlying JWKSManager)
    auth_service: TokenValidator = AuthService(
        decoder=decoder, extractor=extractor, health_checker=decoder
    )

    try:
        await jwks_manager.refresh_keys()
    except Exception:
        logger.exception("auth_service_init_failed")
        raise

    logger.info(
        "auth_service_ready",
        issuer=issuer,
        allowed_clients=settings.allowed_clients,
        audience=settings.audience or None,
    )
    app_state.auth_service = auth_service


async def init_oauth_provider(
    app_state: State, settings: KeycloakSettings, http_client: httpx.AsyncClient
) -> None:
    """Initialize OAuth provider for token operations."""
    provider: OAuthProvider = KeycloakClient(settings, http_client)
    app_state.oauth_provider = provider


async def shutdown_services(
    services: list[tuple[str, CleanupFn]],
) -> None:
    """Graceful shutdown in reverse initialization order."""
    for name, close in reversed(services):
        try:
            await close()
        except Exception:
            logger.exception("shutdown_failed", service=name)


def register_middleware(app: FastAPI, settings: ServerSettings) -> None:
    """Register middleware. ORDER MATTERS: execute in REVERSE add order.

    A request crosses them from the last added to the first, then reaches
    the routes; the response goes back the other way:
    Logging → TrustedHost → SecureHeaders → CORS → BodySizeLimit →
    UnhandledException → routes.
    """
    # Closest to the routes: an unexpected exception becomes a 500 here, and
    # on its way out the 500 gets CORS, security headers and X-Request-ID
    # like any other response.
    app.add_middleware(UnhandledExceptionMiddleware)

    # Inside CORS, so its 413 gets the same headers as any other error.
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=settings.max_body_size)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
        # The browser hides from JavaScript the headers CORS does not
        # expose: without this a frontend cannot show the request id of
        # a failed request.
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.add_middleware(SecureHeadersMiddleware)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts,
    )

    # Outermost: sees every request first and every response last. Docker's
    # HEALTHCHECK and the orchestrator call the health probes all day:
    # their request lines go to DEBUG.
    app.add_middleware(LoggingMiddleware, quiet_prefixes=[health_router.prefix])
