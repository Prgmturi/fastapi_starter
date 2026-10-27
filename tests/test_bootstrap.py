"""Tests for bootstrap.py — composition root service initialization.

Module under test: src/fastapi_starter/bootstrap.py
Layer: Application integration (composition root)

WHY these tests exist: bootstrap.py wires all the concrete implementations
together. It is the only place where concrete classes appear. We verify
the wiring and error handling — particularly that partial initialization
failures properly clean up already-initialized resources.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from jwt.algorithms import RSAAlgorithm
from starlette.datastructures import State
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fastapi_starter.adapters.keycloak.client import KeycloakClient
from fastapi_starter.bootstrap import (
    create_keycloak_http_client,
    init_auth_service,
    init_database,
    init_oauth_provider,
    register_middleware,
    shutdown_services,
)
from fastapi_starter.core.body_limit import BodySizeLimitMiddleware
from fastapi_starter.core.config import (
    DatabaseSettings,
    KeycloakSettings,
    ServerSettings,
)
from fastapi_starter.core.database import DatabaseManager
from fastapi_starter.core.error_middleware import UnhandledExceptionMiddleware
from fastapi_starter.core.logging import LoggingMiddleware
from fastapi_starter.core.security import SecureHeadersMiddleware
from fastapi_starter.main import create_app, lifespan


@pytest.fixture
async def http_client():
    """Real client, never used for requests: only passed around and inspected."""
    async with httpx.AsyncClient() as client:
        yield client


class TestInitDatabase:
    """init_database() — database initialization.

    WHY: Called at startup. If it fails, the app must not start
    with a half-initialized database connection.
    """

    @patch("fastapi_starter.bootstrap.DatabaseManager")
    async def test_creates_manager_and_connects(self, mock_database_manager):
        """[HP] Creates DatabaseManager, calls connect(), stores in state."""
        mock_manager = AsyncMock()
        mock_manager.connect = AsyncMock()
        mock_manager.health_check = AsyncMock(return_value=True)
        mock_database_manager.return_value = mock_manager

        state = State()
        settings = DatabaseSettings()
        result = await init_database(state, settings)

        mock_manager.connect.assert_called_once()
        mock_manager.health_check.assert_called_once()
        assert state.db_manager is mock_manager
        assert result is mock_manager

    @patch("fastapi_starter.bootstrap.DatabaseManager")
    async def test_health_check_failure_disconnects_and_raises(
        self, mock_database_manager
    ):
        """[EC] health_check fails -> disconnect called, exception propagates.

        WHY: Ensures no resource leak if DB is unreachable at startup.
        """
        mock_manager = AsyncMock()
        mock_manager.connect = AsyncMock()
        mock_manager.health_check = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_manager.disconnect = AsyncMock()
        mock_database_manager.return_value = mock_manager

        state = State()
        settings = DatabaseSettings()
        with pytest.raises(RuntimeError, match="DB down"):
            await init_database(state, settings)

        mock_manager.disconnect.assert_called_once()

    @patch("fastapi_starter.bootstrap.DatabaseManager")
    async def test_logs_the_url_without_the_password(
        self, mock_database_manager, monkeypatch
    ):
        """[SEC] database_connected names the database, hides the password.

        WHY a fake logger: module loggers are cached on first use
        (cache_logger_on_first_use), so capture_logs cannot see them.
        """
        mock_database_manager.return_value = AsyncMock()
        logger = MagicMock()
        monkeypatch.setattr("fastapi_starter.bootstrap.logger", logger)

        await init_database(State(), DatabaseSettings(password="db-secret-value"))

        logger.info.assert_called_once_with(
            "database_connected",
            url="postgresql+asyncpg://postgres:***@localhost:5432/appbase",
        )


class TestCreateKeycloakHttpClient:
    """create_keycloak_http_client() — the client shared by Keycloak adapters."""

    async def test_uses_request_timeout_from_settings(self):
        """[HP] Timeout comes from KEYCLOAK_REQUEST_TIMEOUT."""
        settings = KeycloakSettings(request_timeout=7)

        async with create_keycloak_http_client(settings) as client:
            assert client.timeout == httpx.Timeout(7)


class TestInitAuthService:
    """init_auth_service() — auth service initialization.

    WHY: Wires JWKSManager -> JWKSTokenDecoder -> AuthService.
    Pre-fetches JWKS keys. If JWKS fetch fails, app must not start.
    """

    @patch("fastapi_starter.bootstrap.AuthService")
    @patch("fastapi_starter.bootstrap.KeycloakClaimExtractor")
    @patch("fastapi_starter.bootstrap.JWKSTokenDecoder")
    @patch("fastapi_starter.bootstrap.JWKSManager")
    async def test_creates_service_and_stores_in_state(
        self,
        mock_jwks_manager,
        mock_decoder,
        mock_extractor,
        mock_auth_service,
        http_client,
    ):
        """[HP] Keys fetched through the given client, service stored in state.

        With default settings the decoder accepts only client_id and does
        not check aud.
        """
        mock_jwks = AsyncMock()
        mock_jwks.refresh_keys = AsyncMock()
        mock_jwks_manager.return_value = mock_jwks

        state = State()
        settings = KeycloakSettings()
        await init_auth_service(state, settings, http_client)

        mock_jwks_manager.assert_called_once_with(settings, http_client)
        mock_decoder.assert_called_once_with(
            key_provider=mock_jwks,
            issuer="http://localhost:8080/realms/fastapi-starter",
            allowed_clients=["fastapi-backend"],
            audience=None,
        )
        mock_jwks.refresh_keys.assert_called_once()
        assert state.auth_service is mock_auth_service.return_value

    @patch("fastapi_starter.bootstrap.AuthService")
    @patch("fastapi_starter.bootstrap.KeycloakClaimExtractor")
    @patch("fastapi_starter.bootstrap.JWKSTokenDecoder")
    @patch("fastapi_starter.bootstrap.JWKSManager")
    async def test_token_policy_from_settings_reaches_decoder(
        self,
        mock_jwks_manager,
        mock_decoder,
        mock_extractor,
        mock_auth_service,
        http_client,
    ):
        """[HP] KEYCLOAK_ALLOWED_CLIENTS and KEYCLOAK_AUDIENCE reach the decoder."""
        mock_jwks_manager.return_value = AsyncMock()

        settings = KeycloakSettings(
            allowed_clients=["fastapi-backend", "web-frontend"],
            audience="fastapi-backend",
        )
        await init_auth_service(State(), settings, http_client)

        _, kwargs = mock_decoder.call_args
        assert kwargs["allowed_clients"] == ["fastapi-backend", "web-frontend"]
        assert kwargs["audience"] == "fastapi-backend"

    @patch("fastapi_starter.bootstrap.AuthService")
    @patch("fastapi_starter.bootstrap.KeycloakClaimExtractor")
    @patch("fastapi_starter.bootstrap.JWKSTokenDecoder")
    @patch("fastapi_starter.bootstrap.JWKSManager")
    async def test_issuer_is_the_public_url(
        self,
        mock_jwks_manager,
        mock_decoder,
        mock_extractor,
        mock_auth_service,
        http_client,
    ):
        """[HP] The decoder expects the iss Keycloak writes: its public address.

        WHY: with the internal address, every token signed by a Keycloak
        published as https://auth.example.com would be refused with 401.
        """
        mock_jwks_manager.return_value = AsyncMock()

        settings = KeycloakSettings(
            host="keycloak", public_url="https://auth.example.com"
        )
        await init_auth_service(State(), settings, http_client)

        _, kwargs = mock_decoder.call_args
        assert kwargs["issuer"] == "https://auth.example.com/realms/fastapi-starter"

    @patch("fastapi_starter.bootstrap.AuthService")
    @patch("fastapi_starter.bootstrap.KeycloakClaimExtractor")
    @patch("fastapi_starter.bootstrap.JWKSTokenDecoder")
    @patch("fastapi_starter.bootstrap.JWKSManager")
    async def test_jwks_refresh_failure_raises_and_leaves_client_open(
        self,
        mock_jwks_manager,
        mock_decoder,
        mock_extractor,
        mock_auth_service,
        http_client,
    ):
        """[EC] refresh_keys fails -> raises, no service in state, client open.

        WHY: the client belongs to the lifespan, which closes it. An adapter
        that closed it would break the other adapters sharing it.
        """
        mock_jwks = AsyncMock()
        mock_jwks.refresh_keys = AsyncMock(side_effect=RuntimeError("JWKS unreachable"))
        mock_jwks_manager.return_value = mock_jwks

        state = State()
        settings = KeycloakSettings()
        with pytest.raises(RuntimeError, match="JWKS unreachable"):
            await init_auth_service(state, settings, http_client)

        assert not hasattr(state, "auth_service")
        assert not http_client.is_closed


class TestInitOAuthProvider:
    """init_oauth_provider() — OAuth provider for the token endpoints."""

    async def test_stores_keycloak_client_in_state(self, http_client):
        """[HP] app_state.oauth_provider is a KeycloakClient."""
        state = State()

        await init_oauth_provider(state, KeycloakSettings(), http_client)

        assert isinstance(state.oauth_provider, KeycloakClient)


class OfflineDatabaseManager(DatabaseManager):
    """The real manager, minus the one query that needs a server.

    connect() builds the engine without connecting: SQLAlchemy opens the
    first connection at the first query, and health_check runs that query.
    """

    async def health_check(self) -> bool:
        return True


@pytest.fixture(scope="module")
def realm_jwks() -> dict[str, Any]:
    """Key set as Keycloak's certs endpoint publishes it, with one key.

    One for the whole module: generating RSA keys is slow.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    return {"keys": [{**jwk, "kid": "key-1", "use": "sig", "alg": "RS256"}]}


class TestServicesReachTheRoutes:
    """What bootstrap.py stores in app.state is what the routes receive.

    WHY: bootstrap.py stores each service in app.state under a name, and a
    getter (get_db_manager, get_auth_service, get_oauth_provider) reads it
    back by the same name. app.state has no types, and the other tests
    replace the getters: with a misspelled name mypy and every test passed,
    while in production each route that needs the service answered 500.
    Here the real lifespan runs with only the network replaced, and the
    routes get their real dependencies.
    """

    @pytest.fixture
    async def started_client(
        self, settings, realm_jwks, monkeypatch
    ) -> AsyncGenerator[httpx.AsyncClient]:
        """Client for the app after its real startup.

        No database (OfflineDatabaseManager), and Keycloak is a fake
        endpoint that serves realm_jwks.
        """

        def keycloak_http_client(_settings: KeycloakSettings) -> httpx.AsyncClient:
            transport = httpx.MockTransport(
                lambda request: httpx.Response(200, json=realm_jwks)
            )
            return httpx.AsyncClient(transport=transport)

        monkeypatch.setattr(
            "fastapi_starter.bootstrap.DatabaseManager", OfflineDatabaseManager
        )
        monkeypatch.setattr(
            "fastapi_starter.main.create_keycloak_http_client", keycloak_http_client
        )
        app = create_app(settings)

        async with (
            lifespan(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client,
        ):
            yield client

    async def test_readiness_gets_the_database_and_the_auth_service(
        self, started_client
    ):
        """[HP] get_db_manager and get_auth_service find what bootstrap.py stored."""
        response = await started_client.get("/health/ready")

        assert response.status_code == 200
        assert response.json()["checks"] == {
            "database": {"status": "healthy"},
            "auth": {"status": "healthy"},
        }

    async def test_login_gets_the_oauth_provider(self, started_client, settings):
        """[HP] get_oauth_provider and get_keycloak_settings find theirs.

        The URL comes from the real KeycloakClient, built from the settings.
        """
        response = await started_client.get(
            "/auth/login",
            params={
                "redirect_uri": "http://localhost:3000/callback",
                "code_challenge": "challenge",
            },
        )

        assert response.status_code == 200
        assert response.json()["authorization_url"].startswith(
            f"{settings.keycloak.auth_url}?"
        )

    async def test_refresh_gets_the_cookie_settings(self, started_client):
        """[HP] get_cookie_settings finds the cookie settings in app.state.

        Without a cookie /auth/refresh answers 401, after reading the
        cookie's name from those settings. A wrong name in the getter gives
        500 instead.
        """
        response = await started_client.post("/auth/refresh")

        assert response.status_code == 401


class TestShutdownServices:
    """shutdown_services() — graceful shutdown.

    WHY: Must call all cleanup functions even if some fail.
    Reverse order ensures dependencies are cleaned up last.
    """

    async def test_calls_all_cleanup_functions(self):
        """[HP] All registered cleanup functions called."""
        fn1 = AsyncMock()
        fn2 = AsyncMock()
        fn3 = AsyncMock()

        await shutdown_services([("svc1", fn1), ("svc2", fn2), ("svc3", fn3)])

        fn1.assert_called_once()
        fn2.assert_called_once()
        fn3.assert_called_once()

    async def test_reverse_order(self):
        """[HP] Cleanup functions called in reverse registration order.

        WHY: Services initialized first may depend on services initialized
        later. Reverse order ensures dependents are shut down first.
        """
        call_order: list[str] = []

        async def fn_a():
            call_order.append("a")

        async def fn_b():
            call_order.append("b")

        async def fn_c():
            call_order.append("c")

        await shutdown_services([("a", fn_a), ("b", fn_b), ("c", fn_c)])

        assert call_order == ["c", "b", "a"]

    async def test_continues_on_failure(self):
        """[EC] One cleanup function raises -> others still called.

        WHY: shutdown must be robust. A failing service should not
        prevent other services from shutting down cleanly.
        """
        fn1 = AsyncMock()
        fn2 = AsyncMock(side_effect=RuntimeError("failed"))
        fn3 = AsyncMock()

        # Should not raise despite fn2 failing
        await shutdown_services([("svc1", fn1), ("svc2", fn2), ("svc3", fn3)])

        # fn3 called first (reversed), then fn2 (fails), then fn1 (still called)
        fn1.assert_called_once()
        fn3.assert_called_once()

    async def test_empty_services_list(self):
        """[EC] Empty list -> no errors, no calls."""
        await shutdown_services([])  # Should not raise


class TestRegisterMiddleware:
    """register_middleware() — the order the middleware runs in.

    WHY: a response gets a middleware's headers only if it passes through
    that middleware. The error middleware must be the closest to the
    routes, or its 500 skips the others.
    """

    def test_error_middleware_is_closest_to_the_routes(self):
        """[HP] From outermost to innermost, as the docstring says."""
        app = FastAPI()

        register_middleware(app, ServerSettings())

        assert [middleware.cls for middleware in app.user_middleware] == [
            LoggingMiddleware,
            TrustedHostMiddleware,
            SecureHeadersMiddleware,
            CORSMiddleware,
            BodySizeLimitMiddleware,
            UnhandledExceptionMiddleware,
        ]
