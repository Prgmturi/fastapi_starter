"""Composition root helpers — service initialization and shutdown."""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import State
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fastapi_starter.core.auth.extractors import KeycloakClaimExtractor
from fastapi_starter.core.auth.jwks import JWKSTokenDecoder
from fastapi_starter.core.auth.jwks_manager import JWKSManager
from fastapi_starter.core.auth.service import AuthService
from fastapi_starter.core.config import (
    DatabaseSettings,
    KeycloakSettings,
    ServerSettings,
)
from fastapi_starter.core.database import DatabaseManager
from fastapi_starter.core.logging import LoggingMiddleware, get_logger
from fastapi_starter.core.security import SecureHeadersMiddleware
from fastapi_starter.features.auth.client import KeycloakClient

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

    logger.info("database_connected", url=settings.url_safe)
    app_state.db_manager = db_manager
    return db_manager


async def init_auth_service(
    app_state: State, settings: KeycloakSettings
) -> JWKSManager:
    """Wire auth adapters to ports, pre-fetch JWKS keys, register in app state."""
    jwks_manager = JWKSManager(settings)
    issuer = f"{settings.server_url}/realms/{settings.realm}"

    decoder = JWKSTokenDecoder(key_provider=jwks_manager, issuer=issuer)
    extractor = KeycloakClaimExtractor(settings.client_id)
    # JWKSTokenDecoder implements both TokenDecoder and HealthCheckable
    # (health_check delegates to the underlying JWKSManager)
    auth_service = AuthService(
        decoder=decoder, extractor=extractor, health_checker=decoder
    )

    try:
        await jwks_manager.refresh_keys()
    except Exception:
        logger.exception("auth_service_init_failed")
        await jwks_manager.close()
        raise

    logger.info("auth_service_ready", issuer=issuer)
    app_state.auth_service = auth_service
    return jwks_manager


async def init_oauth_provider(
    app_state: State, settings: KeycloakSettings
) -> KeycloakClient:
    """Initialize OAuth provider for token operations."""
    client = KeycloakClient(settings)
    app_state.oauth_provider = client
    return client


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
    """Register middleware. ORDER MATTERS: execute in REVERSE add order."""
    # CORS (executes last)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    app.add_middleware(SecureHeadersMiddleware)

    # TrustedHostMiddleware (executes after secure headers)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts,
    )

    # Logging (executes first)
    app.add_middleware(LoggingMiddleware)
