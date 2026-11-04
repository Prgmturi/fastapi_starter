"""Composition root helpers — service initialization and shutdown.

start_services() is the one place that knows which services the app has:
another identity provider changes this module, not main.py.

Every adapter goes into app.state through the StateKey of its port, next
to the getter that reads it (``OAUTH_PROVIDER.set(state, KeycloakClient(...))``):
mypy checks there that the adapter still matches the port.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import State
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fastapi_starter.adapters.keycloak.client import KeycloakClient
from fastapi_starter.adapters.keycloak.extractors import KeycloakClaimExtractor
from fastapi_starter.adapters.keycloak.jwks import JWKSTokenDecoder
from fastapi_starter.adapters.keycloak.jwks_manager import JWKSManager
from fastapi_starter.core.auth.dependencies import AUTH_SERVICE
from fastapi_starter.core.auth.service import AuthService
from fastapi_starter.core.body_limit import BodySizeLimitMiddleware
from fastapi_starter.core.config import (
    DatabaseSettings,
    KeycloakSettings,
    ServerSettings,
    Settings,
)
from fastapi_starter.core.database import DatabaseManager, database_url
from fastapi_starter.core.database.dependencies import DB_MANAGER
from fastapi_starter.core.error_middleware import UnhandledExceptionMiddleware
from fastapi_starter.core.logging import (
    REQUEST_ID_HEADER,
    LoggingMiddleware,
    get_logger,
)
from fastapi_starter.core.security import SecureHeadersMiddleware
from fastapi_starter.features.auth.router import OAUTH_PROVIDER
from fastapi_starter.features.health.router import health_router

logger = get_logger(__name__)

CleanupFn = Callable[[], Awaitable[Any]]


def _log_start_failure(event: str, error: Exception) -> None:
    """One error line for a service that does not start.

    No traceback: uvicorn prints it when the startup fails. The line names
    the cause of a wrapped error, as the readiness log does.
    """
    cause = error.__cause__ or error
    logger.error(event, error_type=type(cause).__name__, error=str(cause))


async def start_services(
    app_state: State, settings: Settings, services: list[tuple[str, CleanupFn]]
) -> None:
    """Open every service, and put each adapter in app state.

    Each service goes into ``services`` as soon as it is open, so the
    caller can close it whatever happens next: a later service that fails
    to start, or a cancellation.
    """
    db_manager = await init_database(app_state, settings.database)
    services.append(("database", db_manager.disconnect))

    # One client for every call to Keycloak: signing keys and tokens.
    # It is registered before the adapters that use it, so a failure
    # while they start still closes it.
    keycloak_http = create_keycloak_http_client(settings.keycloak)
    services.append(("keycloak_http_client", keycloak_http.aclose))

    await init_auth_service(app_state, settings.keycloak, keycloak_http)
    await init_oauth_provider(app_state, settings.keycloak, keycloak_http)


async def init_database(
    app_state: State, settings: DatabaseSettings
) -> DatabaseManager:
    """Create connection pool, verify connectivity, register in app state."""
    db_manager = DatabaseManager(settings)
    await db_manager.connect()

    try:
        await db_manager.health_check()
    except Exception as e:
        _log_start_failure("database_connection_failed", e)
        await db_manager.disconnect()
        raise

    logger.info(
        "database_connected",
        url=database_url(settings).render_as_string(hide_password=True),
    )
    # app.state holds the port, for the routes. The lifespan gets the
    # manager itself, because disconnect() is not part of the port.
    DB_MANAGER.set(app_state, db_manager)
    return db_manager


def create_keycloak_http_client(settings: KeycloakSettings) -> httpx.AsyncClient:
    """HTTP client shared by every Keycloak adapter: one connection pool.

    The adapters only use it. start_services() creates it, and the
    lifespan closes it.
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
    auth_service = AuthService(
        decoder=decoder, extractor=extractor, health_checker=decoder
    )

    try:
        await jwks_manager.refresh_keys()
    except Exception as e:
        _log_start_failure("auth_service_init_failed", e)
        raise

    logger.info(
        "auth_service_ready",
        issuer=issuer,
        allowed_clients=settings.allowed_clients,
        audience=settings.audience or None,
    )
    AUTH_SERVICE.set(app_state, auth_service)


async def init_oauth_provider(
    app_state: State, settings: KeycloakSettings, http_client: httpx.AsyncClient
) -> None:
    """Initialize OAuth provider for token operations."""
    OAUTH_PROVIDER.set(app_state, KeycloakClient(settings, http_client))


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
        # a failed request, or read when to retry a 503.
        expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
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
