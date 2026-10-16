"""Tests for setup.py — composition root service initialization.

Module under test: src/fastapi_starter/setup.py
Layer: Application integration (composition root)

WHY these tests exist: setup.py wires all the concrete implementations
together. It is the only place where concrete classes appear. We verify
the wiring and error handling — particularly that partial initialization
failures properly clean up already-initialized resources.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.datastructures import State

from fastapi_starter.core.config import DatabaseSettings, KeycloakSettings
from fastapi_starter.features.auth.client import KeycloakClient
from fastapi_starter.setup import (
    create_keycloak_http_client,
    init_auth_service,
    init_database,
    init_oauth_provider,
    shutdown_services,
)


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

    @patch("fastapi_starter.setup.DatabaseManager")
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

    @patch("fastapi_starter.setup.DatabaseManager")
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

    @patch("fastapi_starter.setup.AuthService")
    @patch("fastapi_starter.setup.KeycloakClaimExtractor")
    @patch("fastapi_starter.setup.JWKSTokenDecoder")
    @patch("fastapi_starter.setup.JWKSManager")
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

    @patch("fastapi_starter.setup.AuthService")
    @patch("fastapi_starter.setup.KeycloakClaimExtractor")
    @patch("fastapi_starter.setup.JWKSTokenDecoder")
    @patch("fastapi_starter.setup.JWKSManager")
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

    @patch("fastapi_starter.setup.AuthService")
    @patch("fastapi_starter.setup.KeycloakClaimExtractor")
    @patch("fastapi_starter.setup.JWKSTokenDecoder")
    @patch("fastapi_starter.setup.JWKSManager")
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
