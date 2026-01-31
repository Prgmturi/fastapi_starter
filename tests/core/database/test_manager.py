"""Tests for DatabaseManager — connection lifecycle and health check.

Module under test: src/fastapi_starter/core/database/manager.py
Layer: Infrastructure adapter (mock SQLAlchemy engine creation)

WHY these tests exist: DatabaseManager manages the connection lifecycle.
We verify connect/disconnect idempotency, property guards (raise before
connect), and health check delegation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastapi_starter.core.config.database import DatabaseSettings
from fastapi_starter.core.database.manager import DatabaseManager


@pytest.fixture
def db_settings() -> DatabaseSettings:
    return DatabaseSettings(
        host="localhost",
        port=5432,
        name="testdb",
        user="test",
        password="test",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def db_manager(db_settings) -> DatabaseManager:
    return DatabaseManager(db_settings)


class TestConnect:
    """DatabaseManager.connect() — engine and session factory creation.

    WHY: Called once at startup. Must be idempotent (safe to call twice).
    We verify that engine and session_factory are set after connect().
    """

    @patch("fastapi_starter.core.database.manager.create_async_engine")
    async def test_creates_engine_and_session_factory(
        self,
        mock_create_engine,
        db_manager,
    ):
        """[HP] After connect(), engine and session_factory are not None."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        await db_manager.connect()

        mock_create_engine.assert_called_once()
        assert db_manager._engine is not None
        assert db_manager._session_factory is not None

    @patch("fastapi_starter.core.database.manager.create_async_engine")
    async def test_idempotent_when_already_connected(
        self,
        mock_create_engine,
        db_manager,
    ):
        """[EC] Second connect() is a no-op (does not create new engine).

        WHY: Prevents resource leaks if lifespan logic calls connect() twice.
        """
        mock_create_engine.return_value = MagicMock()

        await db_manager.connect()
        await db_manager.connect()

        mock_create_engine.assert_called_once()


class TestDisconnect:
    """DatabaseManager.disconnect() — resource cleanup.

    WHY: Called at shutdown. Must dispose engine and clear references.
    """

    @patch("fastapi_starter.core.database.manager.create_async_engine")
    async def test_disposes_engine_and_clears_references(
        self,
        mock_create_engine,
        db_manager,
    ):
        """[HP] After disconnect(), engine and session_factory are None."""
        mock_engine = AsyncMock()
        mock_create_engine.return_value = mock_engine

        await db_manager.connect()
        await db_manager.disconnect()

        mock_engine.dispose.assert_called_once()
        assert db_manager._engine is None
        assert db_manager._session_factory is None

    async def test_noop_when_not_connected(self, db_manager):
        """[EC] disconnect() when never connected is safe (no error)."""
        await db_manager.disconnect()  # Should not raise


class TestProperties:
    """Engine and session_factory property guards.

    WHY: Accessing engine or session_factory before connect() should
    fail fast with a clear RuntimeError, not return None silently.
    """

    def test_engine_raises_before_connect(self, db_manager):
        """[EC] Accessing .engine before connect() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db_manager.engine

    def test_session_factory_raises_before_connect(self, db_manager):
        """[EC] Accessing .session_factory before connect() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db_manager.session_factory


class TestHealthCheck:
    """DatabaseManager.health_check() — SELECT 1 probe.

    WHY: The readiness endpoint depends on this. We verify it uses
    the session factory and executes a query.
    """

    @patch("fastapi_starter.core.database.manager.create_async_engine")
    async def test_returns_true_on_success(self, mock_create_engine, db_manager):
        """[HP] SELECT 1 succeeds -> returns True."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        await db_manager.connect()
        db_manager._session_factory = MagicMock(return_value=mock_session)

        result = await db_manager.health_check()

        assert result is True
        mock_session.execute.assert_called_once()

    async def test_raises_when_not_connected(self, db_manager):
        """[EC] health_check() before connect() raises RuntimeError."""
        with pytest.raises(RuntimeError, match="not connected"):
            await db_manager.health_check()


class TestDatabaseProviderProtocol:
    """Contract test: DatabaseManager satisfies DatabaseProvider.

    WHY: Dependencies use DatabaseProvider Protocol, not concrete class.
    """

    def test_implements_database_provider_protocol(self, db_manager):
        """[CT] DatabaseManager structurally satisfies DatabaseProvider."""
        # DatabaseProvider is not @runtime_checkable, so we verify
        # the required methods exist with correct signatures.
        assert hasattr(db_manager, "health_check")
        assert callable(db_manager.health_check)
        assert hasattr(type(db_manager), "session_factory")
        assert isinstance(
            type(db_manager).session_factory,
            property,
        )
