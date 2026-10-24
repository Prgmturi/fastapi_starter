"""BaseRepository on a real Postgres — pages stay stable.

Module under test: src/fastapi_starter/core/database/repository.py
Layer: Infrastructure, real database

WHY: without ORDER BY, Postgres returns rows in the order it finds them on
disk, and an UPDATE writes a new version of the row at the end. Measured on
21 October: page 1 [1, 2, 3], row 1 updated, page 2 [5, 6, 1].
"""

import pytest
from sqlalchemy import update

from tests.core.database.fakes import FakeModel, FakeRepository


class TestPagesOnPostgres:
    @pytest.fixture(autouse=True)
    async def six_rows(self, db_manager):
        """fake_model with the rows 1 to 6, dropped after the test."""
        table = FakeModel.__table__
        async with db_manager.engine.begin() as connection:
            await connection.run_sync(table.drop, checkfirst=True)
            await connection.run_sync(table.create)
        async with db_manager.session_factory.begin() as session:
            session.add_all(FakeModel(id=i, name=f"row {i}") for i in range(1, 7))
        yield
        async with db_manager.engine.begin() as connection:
            await connection.run_sync(table.drop)

    async def page(self, db_manager, offset: int) -> list[int]:
        async with db_manager.session_factory() as session:
            rows = await FakeRepository(session).get_page(limit=3, offset=offset)
            return [row.id for row in rows]

    async def test_update_between_pages_skips_and_repeats_nothing(self, db_manager):
        """[EC] Row 1 updated between page 1 and page 2 -> [1, 2, 3], [4, 5, 6]."""
        first = await self.page(db_manager, offset=0)
        async with db_manager.session_factory.begin() as session:
            await session.execute(
                update(FakeModel).where(FakeModel.id == 1).values(name="changed")
            )
        second = await self.page(db_manager, offset=3)

        assert (first, second) == ([1, 2, 3], [4, 5, 6])
