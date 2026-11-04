"""Tests for DatabaseManager — connection lifecycle and health check.

Module under test: src/fastapi_starter/core/database/manager.py
Layer: Infrastructure adapter (real engines: they connect lazily)

WHY these tests exist: DatabaseManager manages the connection lifecycle.
We verify connect/disconnect idempotency, property guards (raise before
connect), health check delegation, and what an unreachable database
becomes.
"""

import asyncio
import time
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from fastapi_starter.core.config.database import DatabaseSettings
from fastapi_starter.core.database import manager as manager_module
from fastapi_starter.core.database.manager import (
    DatabaseManager,
    connect_or_unavailable,
)
from fastapi_starter.core.exceptions import ServiceUnavailableError


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

    async def test_creates_engine_and_session_factory(self, db_manager):
        """[HP] After connect(), engine and session_factory are not None."""
        await db_manager.connect()
        try:
            assert db_manager._engine is not None
            assert db_manager._session_factory is not None
        finally:
            await db_manager.disconnect()

    @patch(
        "fastapi_starter.core.database.manager.create_async_engine",
        wraps=create_async_engine,
    )
    async def test_idempotent_when_already_connected(
        self,
        mock_create_engine,
        db_manager,
    ):
        """[EC] Second connect() is a no-op (does not create new engine).

        WHY: Prevents resource leaks if lifespan logic calls connect() twice.
        """
        await db_manager.connect()
        await db_manager.connect()
        await db_manager.disconnect()

        mock_create_engine.assert_called_once()


class TestConnectTimeout:
    """A database host that accepts the connection and never answers.

    WHY: asyncpg waits 60 seconds by default. At startup the lifespan stays
    blocked for that long before it reports the error, and so does any
    request that needs a new connection.
    """

    async def test_unresponsive_host_fails_within_connect_timeout(self, silent_port):
        """[EC] connect_timeout=0.5 -> 503 after about half a second."""
        manager = DatabaseManager(
            DatabaseSettings(host="127.0.0.1", port=silent_port, connect_timeout=0.5)
        )
        await manager.connect()
        started = time.monotonic()
        try:
            with pytest.raises(ServiceUnavailableError) as raised:
                # Stops the test if connect_timeout does not reach asyncpg:
                # that TimeoutError would have no cause
                async with asyncio.timeout(5):
                    await manager.health_check()
        finally:
            await manager.disconnect()

        assert time.monotonic() - started < 2
        assert isinstance(raised.value.__cause__, TimeoutError)


class TestUnreachableDatabase:
    """Postgres refuses the connection, or does not answer: a 503.

    WHY: asyncpg raises OSErrors that SQLAlchemy does not wrap. A route
    that needed a connection answered 500 "An unexpected error occurred."
    and logged a traceback of about 190 lines, at each request, and the
    client could not tell that the same request can succeed once the
    database is back (tried on 3 November 2026).
    """

    @pytest.fixture
    def logger(self, monkeypatch):
        """Records the module's log calls.

        WHY a fake: module loggers are cached on first use
        (cache_logger_on_first_use), so capture_logs cannot see them.
        """
        fake = MagicMock()
        monkeypatch.setattr(manager_module, "logger", fake)
        return fake

    @pytest.fixture
    async def refused(self, closed_port) -> ServiceUnavailableError:
        """What health_check() raises with nothing listening on the port."""
        manager = DatabaseManager(DatabaseSettings(host="127.0.0.1", port=closed_port))
        await manager.connect()
        try:
            with pytest.raises(ServiceUnavailableError) as raised:
                await manager.health_check()
        finally:
            await manager.disconnect()
        return raised.value

    async def test_refused_connection_is_unavailable(self, refused):
        """[EC] Connection refused -> 503 for the database, the cause kept."""
        assert refused.status_code == 503
        assert refused.details == {"service": "database"}
        assert isinstance(refused.__cause__, ConnectionRefusedError)

    async def test_says_when_to_retry(self, refused):
        """[EC] The 503 carries Retry-After, in seconds."""
        assert refused.headers == {"Retry-After": "5"}

    async def test_logs_one_line_with_the_cause(self, logger, closed_port):
        """[EC] One error line naming the type, instead of a traceback."""
        manager = DatabaseManager(DatabaseSettings(host="127.0.0.1", port=closed_port))
        await manager.connect()
        try:
            with pytest.raises(ServiceUnavailableError):
                await manager.health_check()
        finally:
            await manager.disconnect()

        logger.error.assert_called_once_with(
            "database_unavailable", error_type="ConnectionRefusedError", error=ANY
        )

    def test_network_error_of_the_listener_is_unavailable(self):
        """[EC] The listener alone: an OSError at connect -> the 503.

        WHY a direct call too: SQLAlchemy runs the listener in a greenlet,
        and coverage does not see the lines it runs there.
        """
        dialect = MagicMock()
        dialect.connect.side_effect = ConnectionRefusedError("Connect call failed")

        with pytest.raises(ServiceUnavailableError) as raised:
            connect_or_unavailable(dialect, MagicMock(), (), {})

        assert isinstance(raised.value.__cause__, ConnectionRefusedError)

    def test_other_connect_errors_pass_unchanged(self):
        """[EC] A wrong password stays itself: a setting to fix, not to retry."""
        dialect = MagicMock()
        dialect.connect.side_effect = asyncpg.exceptions.InvalidPasswordError(
            'password authentication failed for user "app"'
        )

        with pytest.raises(asyncpg.exceptions.InvalidPasswordError):
            connect_or_unavailable(dialect, MagicMock(), (), {})


class TestDisconnect:
    """DatabaseManager.disconnect() — resource cleanup.

    WHY: Called at shutdown. Must dispose engine and clear references.
    """

    async def test_disposes_engine_and_clears_references(self, db_manager):
        """[HP] After disconnect(), engine and session_factory are None."""
        await db_manager.connect()
        with patch.object(AsyncEngine, "dispose", autospec=True) as dispose:
            await db_manager.disconnect()

        dispose.assert_awaited_once()
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

    async def test_returns_true_on_success(self, db_manager):
        """[HP] SELECT 1 succeeds -> returns True."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        await db_manager.connect()
        db_manager._session_factory = MagicMock(return_value=mock_session)
        try:
            result = await db_manager.health_check()
        finally:
            await db_manager.disconnect()

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
