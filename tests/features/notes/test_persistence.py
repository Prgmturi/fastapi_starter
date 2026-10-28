"""Tests for the persistence of notes — the SQL the repository builds.

Module under test: src/fastapi_starter/features/notes/persistence/
Layer: Adapter of the domain's port (mock session, SQL compiled for Postgres)

WHY these tests exist: the owner check lives in the SQL itself. A query
without "AND notes.owner_id = ..." would hand any note to anyone who knows
its id, and the domain could not notice. These tests read the statement;
tests/integration/test_notes.py runs it on a real Postgres.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from fastapi_starter.features.notes.domain.note import Note
from fastapi_starter.features.notes.domain.protocols import NoteRepository
from fastapi_starter.features.notes.persistence.models import NoteRow
from fastapi_starter.features.notes.persistence.repository import (
    SqlNoteRepository,
    to_note,
)
from tests.features.notes.conftest import OWNER

NOTE_ID = UUID("12345678-1234-5678-1234-567812345678")
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
NOTE = Note(
    id=NOTE_ID,
    owner_id=OWNER,
    title="Groceries",
    body="milk",
    created_at=NOW,
    updated_at=NOW,
)


def row_of(note: Note) -> NoteRow:
    return NoteRow(
        id=note.id,
        owner_id=note.owner_id,
        title=note.title,
        body=note.body,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@pytest.fixture
def session() -> AsyncMock:
    """An AsyncSession that records the statements and returns no rows."""
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.rowcount = 1
    session.execute.return_value = result
    return session


def executed_sql(session: AsyncMock) -> str:
    """The statement passed to session.execute, as Postgres SQL on one line."""
    statement = session.execute.call_args.args[0]
    sql = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(sql).split())


class TestPort:
    def test_implements_note_repository(self, session):
        """[CT] SqlNoteRepository is a NoteRepository (the domain's port)."""
        assert isinstance(SqlNoteRepository(session), NoteRepository)


class TestToNote:
    def test_every_field_is_carried(self):
        """[HP] A row becomes the same Note, field by field."""
        assert to_note(row_of(NOTE)) == NOTE


class TestPage:
    async def test_owner_order_limit_offset(self, session):
        """[SEC] Only the owner's rows, oldest first, then id, one page."""
        await SqlNoteRepository(session).page(OWNER, limit=5, offset=10)

        assert executed_sql(session).endswith(
            f"WHERE notes.owner_id = '{OWNER}' "
            "ORDER BY notes.created_at, notes.id LIMIT 5 OFFSET 10"
        )

    async def test_rows_become_notes(self, session):
        """[HP] The rows of the page come back as Note."""
        session.execute.return_value.scalars.return_value.all.return_value = [
            row_of(NOTE)
        ]

        assert await SqlNoteRepository(session).page(OWNER, 5, 0) == [NOTE]


class TestGet:
    async def test_id_and_owner_in_the_query(self, session):
        """[SEC] The owner is part of the WHERE, not checked afterwards."""
        await SqlNoteRepository(session).get(OWNER, NOTE_ID)

        assert executed_sql(session).endswith(
            f"WHERE notes.id = '{NOTE_ID}' AND notes.owner_id = '{OWNER}'"
        )

    async def test_no_row_is_none(self, session):
        """[EC] Missing, or another user's: None."""
        assert await SqlNoteRepository(session).get(OWNER, NOTE_ID) is None

    async def test_row_becomes_note(self, session):
        """[HP] The row found comes back as Note."""
        session.execute.return_value.scalar_one_or_none.return_value = row_of(NOTE)

        assert await SqlNoteRepository(session).get(OWNER, NOTE_ID) == NOTE


class TestAdd:
    async def test_row_added_and_flushed(self, session):
        """[HP] A row with the note's fields, flushed in the request's transaction."""
        await SqlNoteRepository(session).add(NOTE)

        row = session.add.call_args.args[0]
        assert to_note(row) == NOTE
        session.flush.assert_awaited_once()


class TestSave:
    async def test_update_by_id_and_owner(self, session):
        """[SEC] UPDATE of title, body and updated_at, for the owner's row only."""
        await SqlNoteRepository(session).save(NOTE)

        sql = executed_sql(session)
        assert sql.startswith("UPDATE notes SET title='Groceries', body='milk', ")
        assert sql.endswith(
            f"WHERE notes.id = '{NOTE_ID}' AND notes.owner_id = '{OWNER}'"
        )

    @pytest.mark.parametrize(("rowcount", "saved"), [(1, True), (0, False)])
    async def test_tells_whether_a_row_changed(self, session, rowcount, saved):
        """[HP] True when the row was there, False when it was gone."""
        session.execute.return_value.rowcount = rowcount

        assert await SqlNoteRepository(session).save(NOTE) is saved


class TestDelete:
    async def test_delete_by_id_and_owner(self, session):
        """[SEC] DELETE of the owner's row only."""
        await SqlNoteRepository(session).delete(OWNER, NOTE_ID)

        assert executed_sql(session) == (
            f"DELETE FROM notes WHERE notes.id = '{NOTE_ID}' "
            f"AND notes.owner_id = '{OWNER}'"
        )

    @pytest.mark.parametrize(("rowcount", "deleted"), [(1, True), (0, False)])
    async def test_tells_whether_a_row_went(self, session, rowcount, deleted):
        """[HP] True when a row was deleted, False when there was none."""
        session.execute.return_value.rowcount = rowcount

        assert await SqlNoteRepository(session).delete(OWNER, NOTE_ID) is deleted
