"""DatabaseManager on a real Postgres — the pool survives a restart.

Module under test: src/fastapi_starter/core/database/manager.py
Layer: FastAPI integration, real database

WHY: a restart or a failover of Postgres closes every connection in the
pool, and the app finds out only when it uses one.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from fastapi_starter.core.database import DbSession, database_url
from tests.integration.settings import IntegrationDatabaseSettings


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
