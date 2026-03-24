"""Tests for setup.py — composition root service initialization.

Module under test: src/fastapi_starter/setup.py
Layer: Application integration (composition root)

WHY these tests exist: setup.py wires all the concrete implementations
together. It is the only place where concrete classes appear. We verify
the wiring and error handling — particularly that partial initialization
failures properly clean up already-initialized resources.
"""

from unittest.mock import AsyncMock, patch

import pytest
from starlette.datastructures import State

from fastapi_starter.core.config import DatabaseSettings, KeycloakSettings
from fastapi_starter.setup import init_auth_service, init_database, shutdown_services


class TestInitDatabase:
    """init_database() — database initialization.

    WHY: Called at startup. If it fails, the app must not start
    with a half-initialized database connection.
    """

    @patch("fastapi_starter.setup.DatabaseManager")
    async def test_creates_manager_and_connects(self, MockManager):
        """[HP] Creates DatabaseManager, calls connect(), stores in state."""
        mock_manager = AsyncMock()
        mock_manager.connect = AsyncMock()
        mock_manager.health_check = AsyncMock(return_value=True)
        MockManager.return_value = mock_manager

        state = State()
        settings = DatabaseSettings()
        result = await init_database(state, settings)

        mock_manager.connect.assert_called_once()
        mock_manager.health_check.assert_called_once()
        assert state.db_manager is mock_manager
        assert result is mock_manager

    @patch("fastapi_starter.setup.DatabaseManager")
    async def test_health_check_failure_disconnects_and_raises(self, MockManager):
        """[EC] health_check fails -> disconnect called, exception propagates.

        WHY: Ensures no resource leak if DB is unreachable at startup.
        """
        mock_manager = AsyncMock()
        mock_manager.connect = AsyncMock()
        mock_manager.health_check = AsyncMock(side_effect=RuntimeError("DB down"))
        mock_manager.disconnect = AsyncMock()
        MockManager.return_value = mock_manager

        state = State()
        settings = DatabaseSettings()
        with pytest.raises(RuntimeError, match="DB down"):
            await init_database(state, settings)

        mock_manager.disconnect.assert_called_once()


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
        self, MockJWKS, MockDecoder, MockExtractor, MockAuthService,
    ):
        """[HP] AuthService stored in app_state.auth_service."""
        mock_jwks = AsyncMock()
        mock_jwks.refresh_keys = AsyncMock()
        MockJWKS.return_value = mock_jwks

        state = State()
        settings = KeycloakSettings()
        result = await init_auth_service(state, settings)

        mock_jwks.refresh_keys.assert_called_once()
        assert hasattr(state, "auth_service")
        assert result is mock_jwks

    @patch("fastapi_starter.setup.AuthService")
    @patch("fastapi_starter.setup.KeycloakClaimExtractor")
    @patch("fastapi_starter.setup.JWKSTokenDecoder")
    @patch("fastapi_starter.setup.JWKSManager")
    async def test_jwks_refresh_failure_closes_manager_and_raises(
        self, MockJWKS, MockDecoder, MockExtractor, MockAuthService,
    ):
        """[EC] refresh_keys fails -> jwks_manager.close() called, raises."""
        mock_jwks = AsyncMock()
        mock_jwks.refresh_keys = AsyncMock(side_effect=RuntimeError("JWKS unreachable"))
        mock_jwks.close = AsyncMock()
        MockJWKS.return_value = mock_jwks

        state = State()
        settings = KeycloakSettings()
        with pytest.raises(RuntimeError, match="JWKS unreachable"):
            await init_auth_service(state, settings)

        mock_jwks.close.assert_called_once()


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
