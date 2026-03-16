"""Tests for BaseRepository — generic CRUD operations.

Module under test: src/fastapi_starter/core/database/repository.py
Layer: Core logic (mock AsyncSession)

WHY these tests exist: BaseRepository is the generic CRUD base class. Every
future entity repository extends it. We verify the CRUD operations delegate
correctly to the session, and the __init_subclass__ guard prevents misuse.
"""

import pytest


class TestInitSubclass:
    """BaseRepository.__init_subclass__ — compile-time validation.

    WHY: If a developer creates a Repository subclass and forgets
    to define `model`, they get a cryptic error at query time.
    __init_subclass__ catches this at class definition time.
    """

    def test_subclass_without_model_raises_type_error(self):
        """[EC] Class without `model` attribute raises TypeError."""
        pytest.skip("Not implemented yet")

    def test_subclass_with_model_succeeds(self):
        """[HP] Class with `model` attribute creates successfully."""
        pytest.skip("Not implemented yet")


class TestGetById:
    """BaseRepository.get_by_id() — single entity lookup.

    WHY: Delegates to session.get(). We verify it passes the model
    class and entity_id correctly.
    """

    async def test_existing_entity_returned(self):
        """[HP] session.get returns entity -> returned to caller."""
        pytest.skip("Not implemented yet")

    async def test_nonexistent_entity_returns_none(self):
        """[EC] session.get returns None -> None to caller."""
        pytest.skip("Not implemented yet")


class TestGetAll:
    """BaseRepository.get_all() — retrieve all entities.

    WHY: Uses select() + execute(). We verify the result is properly
    unpacked from SQLAlchemy's Result -> ScalarResult -> list.
    """

    async def test_returns_all_entities(self):
        """[HP] Multiple entities returned as list."""
        pytest.skip("Not implemented yet")

    async def test_empty_table_returns_empty_list(self):
        """[EC] No entities -> empty list (not None)."""
        pytest.skip("Not implemented yet")


class TestCreate:
    """BaseRepository.create() — persist new entity.

    WHY: Uses add() + flush(). We verify:
    1. session.add is called (entity added to unit of work)
    2. session.flush is called (SQL sent to DB within transaction)
    3. The entity is returned (not a copy, not None)
    """

    async def test_entity_added_and_flushed(self):
        """[HP] session.add and session.flush called in order."""
        pytest.skip("Not implemented yet")

    async def test_returns_same_entity(self):
        """[HP] Returns the same entity object that was passed in."""
        pytest.skip("Not implemented yet")


class TestDelete:
    """BaseRepository.delete() — remove entity.

    WHY: Uses delete() + flush(). Verify both operations called.
    """

    async def test_entity_deleted_and_flushed(self):
        """[HP] session.delete and session.flush called."""
        pytest.skip("Not implemented yet")
