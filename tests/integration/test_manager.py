"""DatabaseManager on a real Postgres — the pool survives a restart.

Module under test: src/fastapi_starter/core/database/manager.py
Layer: FastAPI integration, real database

WHY: a restart or a failover of Postgres closes every connection in the
pool, and the app finds out only when it uses one.
"""

import time

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from fastapi_starter.core.database import DbSession, database_url
from tests.integration.settings import IntegrationDatabaseSettings
from tests.test_exception_handlers import assert_problem


async def close_other_connections(settings: IntegrationDatabaseSettings) -> int:
    """Close, from the server, the other client connections to the test database.

    What a restart does to the pool, without stopping the container. Only
    the test database: locally the same server holds the app's database.
    Returns how many connections were closed.
    """
    engine = create_async_engine(database_url(settings), poolclass=NullPool)
    async with engine.connect() as connection:
        # 5000: wait up to 5 s for each backend to exit, so the next query
        # cannot reach it while it is still shutting down
        closed = await connection.scalars(
            text(
                "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity "
                "WHERE datname = current_database() "
                "AND backend_type = 'client backend' AND pid <> pg_backend_pid()"
            )
        )
        count = closed.all().count(True)
    await engine.dispose()
    return count


async def running_queries(settings: IntegrationDatabaseSettings, marker: str) -> int:
    """How many queries with marker in their text still run on the server."""
    engine = create_async_engine(database_url(settings), poolclass=NullPool)
    async with engine.connect() as connection:
        running = await connection.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND state = 'active' "
                "AND query LIKE :pattern AND pid <> pg_backend_pid()"
            ),
            {"pattern": f"%{marker}%"},
        )
    await engine.dispose()
    return running


class TestServerClosedConnections:
    """Postgres closes the connection waiting in the pool, as in a restart.

    WHY: a dead connection in the pool fails the request that gets it,
    with 500, unless the pool checks it first.
    """

    @pytest.fixture
    def ping_app(self, app):
        """The test app plus GET /ping, which runs one query."""

        @app.get("/ping")
        async def ping(session: DbSession) -> dict[str, int]:
            return {"value": await session.scalar(text("SELECT 1"))}

        return app

    async def test_request_after_restart_succeeds(
        self, ping_app, client, database_settings
    ):
        """[EC] Pooled connection closed by Postgres -> the next request gets 200."""
        # After this request one connection waits in the pool
        assert (await client.get("/ping")).status_code == 200
        assert await close_other_connections(database_settings) == 1

        response = await client.get("/ping")

        assert response.status_code == 200
        assert response.json() == {"value": 1}


class TestQueryTimeout:
    """A query that runs longer than command_timeout.

    WHY: without a limit a slow query holds its connection, and its
    request, for as long as it runs. A few of them empty the pool.
    """

    @pytest.fixture
    def database_settings(self, database_settings):
        """A one-second limit, so the test stays short."""
        return database_settings.model_copy(update={"command_timeout": 1})

    @pytest.fixture
    def slow_app(self, app):
        """The test app plus GET /slow, whose query takes 3 seconds."""

        @app.get("/slow")
        async def slow(session: DbSession) -> dict[str, str]:
            await session.execute(text("SELECT pg_sleep(3), 'slow-route'"))
            return {"status": "done"}

        return app

    async def test_slow_query_is_stopped_at_the_limit(
        self, slow_app, client, database_settings
    ):
        """[EC] 3 s query, 1 s limit -> 500 after about a second, and the
        query no longer runs on the server either.
        """
        started = time.monotonic()

        response = await client.get("/slow")

        assert_problem(response, 500)
        assert time.monotonic() - started < 2.5
        assert await running_queries(database_settings, "slow-route") == 0
