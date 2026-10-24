"""Tests for BaseRepository — generic CRUD operations.

Module under test: src/fastapi_starter/core/database/repository.py
Layer: Core logic (mock AsyncSession)

WHY these tests exist: BaseRepository is the generic CRUD base class. Every
future entity repository extends it. We verify the CRUD operations delegate
correctly to the session, and the __init_subclass__ guard prevents misuse.
"""

from unittest.mock import MagicMock

import pytest

from fastapi_starter.core.database.repository import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    BaseRepository,
)
from tests.core.database.fakes import FakeModel


def executed_sql(mock_session) -> str:
    """The statement the repository passed to session.execute, as SQL."""
    statement = mock_session.execute.call_args.args[0]
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


class TestInitSubclass:
    """BaseRepository.__init_subclass__ — compile-time validation.

    WHY: If a developer creates a Repository subclass and forgets
    to define `model`, they get a cryptic error at query time.
    __init_subclass__ catches this at class definition time.
    """

    def test_subclass_without_model_raises_type_error(self):
        """[EC] Class without `model` attribute raises TypeError."""
        with pytest.raises(TypeError, match="must define a 'model'"):

            class BadRepository(BaseRepository):  # type: ignore[type-arg]
                pass

    def test_subclass_with_model_succeeds(self, test_repository):
        """[HP] Class with `model` attribute creates successfully."""
        # FakeRepository from conftest is the positive case
        assert test_repository is not None


class TestGetById:
    """BaseRepository.get_by_id() — single entity lookup.

    WHY: Delegates to session.get(). We verify it passes the model
    class and entity_id correctly.
    """

    async def test_existing_entity_returned(self, test_repository, mock_session):
        """[HP] session.get returns entity -> returned to caller."""
        entity = FakeModel(id=1, name="test")
        mock_session.get.return_value = entity

        result = await test_repository.get_by_id(1)

        assert result is entity
        mock_session.get.assert_called_once_with(FakeModel, 1)

    async def test_nonexistent_entity_returns_none(self, test_repository, mock_session):
        """[EC] session.get returns None -> None to caller."""
        mock_session.get.return_value = None

        result = await test_repository.get_by_id(999)

        assert result is None


class TestGetPage:
    """BaseRepository.get_page() — one page of entities.

    WHY: get_all() read the whole table in one go, in no defined order.
    Postgres returns rows in the order it finds them, and an UPDATE moves
    a row: page 1 [1, 2, 3], row 1 updated, page 2 [5, 6, 1]. Row 4 was
    never shown and row 1 twice.
    """

    @pytest.fixture(autouse=True)
    def result(self, mock_session) -> MagicMock:
        """What execute() returns: no rows, unless a test puts some."""
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result
        return result

    async def test_returns_the_entities(self, test_repository, result):
        """[HP] The rows of the page, as a list."""
        entities = [FakeModel(id=1, name="a"), FakeModel(id=2, name="b")]
        result.scalars.return_value.all.return_value = entities

        assert await test_repository.get_page() == entities

    async def test_sorted_by_primary_key(self, test_repository, mock_session):
        """[HP] ORDER BY the primary key, then LIMIT and OFFSET."""
        await test_repository.get_page(limit=3, offset=6)

        sql = " ".join(executed_sql(mock_session).split())
        assert sql.endswith("ORDER BY fake_model.id LIMIT 3 OFFSET 6")

    async def test_first_page_by_default(self, test_repository, mock_session):
        """[HP] No arguments -> the first DEFAULT_PAGE_SIZE rows."""
        await test_repository.get_page()

        assert f"LIMIT {DEFAULT_PAGE_SIZE} OFFSET 0" in executed_sql(mock_session)

    async def test_largest_page_accepted(self, test_repository, mock_session):
        """[HP] limit=MAX_PAGE_SIZE is still a valid page."""
        await test_repository.get_page(limit=MAX_PAGE_SIZE)

        assert f"LIMIT {MAX_PAGE_SIZE} " in executed_sql(mock_session)

    @pytest.mark.parametrize(
        ("limit", "offset"),
        [(0, 0), (MAX_PAGE_SIZE + 1, 0), (10, -1)],
        ids=["empty-page", "page-too-large", "negative-offset"],
    )
    async def test_out_of_range_refused(
        self, test_repository, mock_session, limit, offset
    ):
        """[EC] A page that makes no sense -> ValueError, no query.

        WHY: a limit of a million is a full table read again. The router
        validates its query parameters (422); this is the last line.
        """
        with pytest.raises(ValueError):
            await test_repository.get_page(limit=limit, offset=offset)

        mock_session.execute.assert_not_called()


class TestCreate:
    """BaseRepository.create() — persist new entity.

    WHY: Uses add() + flush(). We verify:
    1. session.add is called (entity added to unit of work)
    2. session.flush is called (SQL sent to DB within transaction)
    3. The entity is returned (not a copy, not None)
    """

    async def test_entity_added_and_flushed(self, test_repository, mock_session):
        """[HP] session.add and session.flush called in order."""
        entity = FakeModel(id=1, name="new")

        await test_repository.create(entity)

        mock_session.add.assert_called_once_with(entity)
        mock_session.flush.assert_called_once()

    async def test_returns_same_entity(self, test_repository, mock_session):
        """[HP] Returns the same entity object that was passed in."""
        entity = FakeModel(id=1, name="new")

        result = await test_repository.create(entity)

        assert result is entity


class TestDelete:
    """BaseRepository.delete() — remove entity.

    WHY: Uses delete() + flush(). Verify both operations called.
    """

    async def test_entity_deleted_and_flushed(self, test_repository, mock_session):
        """[HP] session.delete and session.flush called."""
        entity = FakeModel(id=1, name="old")

        await test_repository.delete(entity)

        mock_session.delete.assert_called_once_with(entity)
        mock_session.flush.assert_called_once()
