"""DbSession on a real Postgres — the commit decides the response.

Module under test: src/fastapi_starter/core/database/dependencies.py
Layer: FastAPI integration, real database

WHY: TestDbSessionInRequest (tests/core/database/test_dependencies.py)
proves the same with a mock session. Here Postgres raises the error
itself, and each test reads back what was really saved.
"""

import pytest
from sqlalchemy import String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from fastapi_starter.core.database import DatabaseManager, DbSession
from tests.test_exception_handlers import assert_problem


class IntegrationBase(DeclarativeBase):
    """Tables of these tests only: Base.metadata, which Alembic reads, stays clean."""


class Item(IntegrationBase):
    __tablename__ = "integration_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


async def saved_names(db_manager: DatabaseManager) -> list[str]:
    """Item names in the database, read in a session of their own."""
    async with db_manager.session_factory() as session:
        names = await session.scalars(select(Item.name).order_by(Item.id))
        return list(names)


class TestCommitDecidesTheResponse:
    """A route that saves two items in one request, through DbSession.

    WHY: a 201 tells the client the data exists. If the commit fails,
    nothing from that request may stay in the database.
    """

    @pytest.fixture(autouse=True)
    async def items_table(self, db_manager):
        """A fresh integration_items table with one row, "taken"."""
        async with db_manager.engine.begin() as connection:
            await connection.run_sync(IntegrationBase.metadata.drop_all)
            await connection.run_sync(IntegrationBase.metadata.create_all)
        async with db_manager.session_factory.begin() as session:
            session.add(Item(name="taken"))
        yield
        async with db_manager.engine.begin() as connection:
            await connection.run_sync(IntegrationBase.metadata.drop_all)

    @pytest.fixture
    def items_app(self, app):
        """The test app plus POST /items, which saves the two names it gets."""

        @app.post("/items", status_code=201)
        async def add_items(names: list[str], session: DbSession) -> list[str]:
            first, second = names
            session.add(Item(name=first))
            # The first INSERT runs now, inside the request's transaction.
            await session.flush()
            # The second is sent by the commit, after the route returns.
            session.add(Item(name=second))
            return names

        return app

    async def test_successful_commit_returns_201_and_saves(
        self, items_app, client, db_manager
    ):
        """[HP] Commit succeeds -> 201, and both rows are in the database."""
        response = await client.post("/items", json=["first", "second"])

        assert response.status_code == 201
        assert await saved_names(db_manager) == ["taken", "first", "second"]

    async def test_failed_commit_returns_500_and_saves_nothing(
        self, items_app, client, db_manager
    ):
        """[EC] The second name is taken: the commit fails -> 500, and the
        first INSERT, already run, is rolled back with it.
        """
        response = await client.post("/items", json=["first", "taken"])

        assert_problem(response, 500)
        assert await saved_names(db_manager) == ["taken"]
