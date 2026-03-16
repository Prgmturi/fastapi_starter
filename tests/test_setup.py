"""Tests for setup.py — composition root service initialization.

Module under test: src/fastapi_starter/setup.py
Layer: Application integration (composition root)

WHY these tests exist: setup.py wires all the concrete implementations
together. It is the only place where concrete classes appear. We verify
the wiring and error handling — particularly that partial initialization
failures properly clean up already-initialized resources.
"""

import pytest


class TestInitDatabase:
    """init_database() — database initialization.

    WHY: Called at startup. If it fails, the app must not start
    with a half-initialized database connection.
    """

    async def test_creates_manager_and_connects(self):
        """[HP] Creates DatabaseManager, calls connect(), stores in state."""
        pytest.skip("Not implemented yet")

    async def test_health_check_failure_disconnects_and_raises(self):
        """[EC] health_check fails -> disconnect called, exception propagates.

        WHY: Ensures no resource leak if DB is unreachable at startup.
        """
        pytest.skip("Not implemented yet")


class TestInitAuthService:
    """init_auth_service() — auth service initialization.

    WHY: Wires JWKSManager -> JWKSTokenDecoder -> AuthService.
    Pre-fetches JWKS keys. If JWKS fetch fails, app must not start.
    """

    async def test_creates_service_and_stores_in_state(self):
        """[HP] AuthService stored in app_state.auth_service."""
        pytest.skip("Not implemented yet")

    async def test_jwks_refresh_failure_closes_manager_and_raises(self):
        """[EC] refresh_keys fails -> jwks_manager.close() called, raises."""
        pytest.skip("Not implemented yet")


class TestShutdownServices:
    """shutdown_services() — graceful shutdown.

    WHY: Must call all cleanup functions even if some fail.
    Reverse order ensures dependencies are cleaned up last.
    """

    async def test_calls_all_cleanup_functions(self):
        """[HP] All registered cleanup functions called."""
        pytest.skip("Not implemented yet")

    async def test_reverse_order(self):
        """[HP] Cleanup functions called in reverse registration order.

        WHY: Services initialized first may depend on services initialized
        later. Reverse order ensures dependents are shut down first.
        """
        pytest.skip("Not implemented yet")

    async def test_continues_on_failure(self):
        """[EC] One cleanup function raises -> others still called.

        WHY: shutdown must be robust. A failing service should not
        prevent other services from shutting down cleanly.
        """
        pytest.skip("Not implemented yet")

    async def test_empty_services_list(self):
        """[EC] Empty list -> no errors, no calls."""
        pytest.skip("Not implemented yet")
