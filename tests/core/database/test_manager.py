"""Tests for DatabaseManager — connection lifecycle and health check.

Module under test: src/fastapi_starter/core/database/manager.py
Layer: Infrastructure adapter (mock SQLAlchemy engine creation)

WHY these tests exist: DatabaseManager manages the connection lifecycle.
We verify connect/disconnect idempotency, property guards (raise before
connect), and health check delegation.
"""

import pytest


class TestConnect:
    """DatabaseManager.connect() — engine and session factory creation.

    WHY: Called once at startup. Must be idempotent (safe to call twice).
    We verify that engine and session_factory are set after connect().
    """

    async def test_creates_engine_and_session_factory(self):
        """[HP] After connect(), engine and session_factory are not None."""
        pytest.skip("Not implemented yet")

    async def test_idempotent_when_already_connected(self):
        """[EC] Second connect() is a no-op (does not create new engine).

        WHY: Prevents resource leaks if lifespan logic calls connect() twice.
        """
        pytest.skip("Not implemented yet")


class TestDisconnect:
    """DatabaseManager.disconnect() — resource cleanup.

    WHY: Called at shutdown. Must dispose engine and clear references.
    """

    async def test_disposes_engine_and_clears_references(self):
        """[HP] After disconnect(), engine and session_factory are None."""
        pytest.skip("Not implemented yet")

    async def test_noop_when_not_connected(self):
        """[EC] disconnect() when never connected is safe (no error)."""
        pytest.skip("Not implemented yet")


class TestProperties:
    """Engine and session_factory property guards.

    WHY: Accessing engine or session_factory before connect() should
    fail fast with a clear RuntimeError, not return None silently.
    """

    def test_engine_raises_before_connect(self):
        """[EC] Accessing .engine before connect() raises RuntimeError."""
        pytest.skip("Not implemented yet")

    def test_session_factory_raises_before_connect(self):
        """[EC] Accessing .session_factory before connect() raises RuntimeError."""
        pytest.skip("Not implemented yet")


class TestHealthCheck:
    """DatabaseManager.health_check() — SELECT 1 probe.

    WHY: The readiness endpoint depends on this. We verify it uses
    the session factory and executes a query.
    """

    async def test_returns_true_on_success(self):
        """[HP] SELECT 1 succeeds -> returns True."""
        pytest.skip("Not implemented yet")

    async def test_raises_when_not_connected(self):
        """[EC] health_check() before connect() raises RuntimeError."""
        pytest.skip("Not implemented yet")


class TestDatabaseProviderProtocol:
    """Contract test: DatabaseManager satisfies DatabaseProvider.

    WHY: Dependencies use DatabaseProvider Protocol, not concrete class.
    """

    def test_implements_database_provider_protocol(self):
        """[CT] DatabaseManager structurally satisfies DatabaseProvider."""
        pytest.skip("Not implemented yet")
