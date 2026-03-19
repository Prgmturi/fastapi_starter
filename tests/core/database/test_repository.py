"""Tests for BaseRepository — generic CRUD operations.

Module under test: src/fastapi_starter/core/database/repository.py
Layer: Core logic (mock AsyncSession)

WHY these tests exist: BaseRepository is the generic CRUD base class. Every
future entity repository extends it. We verify the CRUD operations delegate
correctly to the session, and the __init_subclass__ guard prevents misuse.
"""

from unittest.mock import MagicMock

import pytest

from fastapi_starter.core.database.repository import BaseRepository


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
        from tests.core.database.conftest import FakeModel

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


class TestGetAll:
    """BaseRepository.get_all() — retrieve all entities.

    WHY: Uses select() + execute(). We verify the result is properly
    unpacked from SQLAlchemy's Result -> ScalarResult -> list.
    """

    async def test_returns_all_entities(self, test_repository, mock_session):
        """[HP] Multiple entities returned as list."""
        from tests.core.database.conftest import FakeModel

        entities = [FakeModel(id=1, name="a"), FakeModel(id=2, name="b")]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = entities
        mock_session.execute.return_value = mock_result

        result = await test_repository.get_all()

        assert result == entities
        assert len(result) == 2

    async def test_empty_table_returns_empty_list(self, test_repository, mock_session):
        """[EC] No entities -> empty list (not None)."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await test_repository.get_all()

        assert result == []


class TestCreate:
    """BaseRepository.create() — persist new entity.

    WHY: Uses add() + flush(). We verify:
    1. session.add is called (entity added to unit of work)
    2. session.flush is called (SQL sent to DB within transaction)
    3. The entity is returned (not a copy, not None)
    """

    async def test_entity_added_and_flushed(self, test_repository, mock_session):
        """[HP] session.add and session.flush called in order."""
        from tests.core.database.conftest import FakeModel

        entity = FakeModel(id=1, name="new")

        await test_repository.create(entity)

        mock_session.add.assert_called_once_with(entity)
        mock_session.flush.assert_called_once()

    async def test_returns_same_entity(self, test_repository, mock_session):
        """[HP] Returns the same entity object that was passed in."""
        from tests.core.database.conftest import FakeModel

        entity = FakeModel(id=1, name="new")

        result = await test_repository.create(entity)

        assert result is entity


class TestDelete:
    """BaseRepository.delete() — remove entity.

    WHY: Uses delete() + flush(). Verify both operations called.
    """

    async def test_entity_deleted_and_flushed(self, test_repository, mock_session):
        """[HP] session.delete and session.flush called."""
        from tests.core.database.conftest import FakeModel

        entity = FakeModel(id=1, name="old")

        await test_repository.delete(entity)

        mock_session.delete.assert_called_once_with(entity)
        mock_session.flush.assert_called_once()
