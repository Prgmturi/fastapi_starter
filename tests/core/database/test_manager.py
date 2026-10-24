"""Tests for DatabaseManager — connection lifecycle and health check.

Module under test: src/fastapi_starter/core/database/manager.py
Layer: Infrastructure adapter (mock SQLAlchemy engine creation)

WHY these tests exist: DatabaseManager manages the connection lifecycle.
We verify connect/disconnect idempotency, property guards (raise before
connect), and health check delegation.
"""

import asyncio
import time
from collections.abc import AsyncIterator
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
    )


@pytest.fixture
def db_manager(db_settings) -> DatabaseManager:
    return DatabaseManager(db_settings)


class TestConnectionUrl:
    """The address the engine connects to, built from the settings.

    WHY: the URL was an f-string, so the password was read as URL syntax.
    With "p@ss" SQLAlchemy took "ss@localhost" as the host, with
    "p@ss:w/rd" startup failed on the port, and "pa%40ss" silently became
    "pa@ss".
    """

    @pytest.mark.parametrize("password", ["p@ss", "p@ss:w/rd", "pa%40ss"])
    async def test_password_is_not_read_as_url_syntax(self, password):
        """[EC] Host, port, database and password reach the engine unchanged."""
        manager = DatabaseManager(
            DatabaseSettings(
                host="db-host", port=5433, name="orders", user="app", password=password
            )
        )

        # The engine connects lazily: creating it opens no connection
        await manager.connect()
        try:
            url = manager.engine.url
        finally:
            await manager.disconnect()

        assert (url.host, url.port, url.database) == ("db-host", 5433, "orders")
        assert (url.username, url.password) == ("app", password)


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


class TestConnectTimeout:
    """A database host that accepts the connection and never answers.

    WHY: asyncpg waits 60 seconds by default. At startup the lifespan stays
    blocked for that long before it reports the error, and so does any
    request that needs a new connection.
    """

    @pytest.fixture
    async def silent_port(self) -> AsyncIterator[int]:
        """A local port that accepts TCP connections and never answers."""

        async def never_answer(reader, writer):
            await reader.read()  # until the client gives up and closes
            writer.close()

        server = await asyncio.start_server(never_answer, "127.0.0.1", 0)
        yield server.sockets[0].getsockname()[1]
        server.close_clients()
        server.close()
        await server.wait_closed()

    async def test_unresponsive_host_fails_within_connect_timeout(self, silent_port):
        """[EC] connect_timeout=0.5 -> TimeoutError after about half a second."""
        manager = DatabaseManager(
            DatabaseSettings(host="127.0.0.1", port=silent_port, connect_timeout=0.5)
        )
        await manager.connect()
        started = time.monotonic()
        try:
            with pytest.raises(TimeoutError):
                # Stops the test if connect_timeout does not reach asyncpg
                async with asyncio.timeout(5):
                    await manager.health_check()
        finally:
            await manager.disconnect()

        assert time.monotonic() - started < 2


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
