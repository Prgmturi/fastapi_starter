from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_starter.features.notes.domain.note import Note
from fastapi_starter.features.notes.persistence.models import NoteRow


def to_note(row: NoteRow) -> Note:
    """The Note of the domain, from its row."""
    return Note(
        id=row.id,
        owner_id=row.owner_id,
        title=row.title,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlNoteRepository:
    """The NoteRepository port on SQLAlchemy, with the session of the request.

    Every query filters by owner in SQL itself, so a note of another user
    is never read, changed or deleted. The session commits when the route
    returns (DbSession), not here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def page(self, owner_id: str, limit: int, offset: int) -> list[Note]:
        # Two notes can share created_at: the id keeps the order the same
        # on every page
        statement = (
            select(NoteRow)
            .where(NoteRow.owner_id == owner_id)
            .order_by(NoteRow.created_at, NoteRow.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return [to_note(row) for row in result.scalars().all()]

    async def get(self, owner_id: str, note_id: UUID) -> Note | None:
        statement = select(NoteRow).where(
            NoteRow.id == note_id, NoteRow.owner_id == owner_id
        )
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return None if row is None else to_note(row)

    async def add(self, note: Note) -> None:
        self._session.add(
            NoteRow(
                id=note.id,
                owner_id=note.owner_id,
                title=note.title,
                body=note.body,
                created_at=note.created_at,
                updated_at=note.updated_at,
            )
        )
        await self._session.flush()

    async def save(self, note: Note) -> bool:
        statement = (
            update(NoteRow)
            .where(NoteRow.id == note.id, NoteRow.owner_id == note.owner_id)
            .values(title=note.title, body=note.body, updated_at=note.updated_at)
        )
        return await self._changed_one(statement)

    async def delete(self, owner_id: str, note_id: UUID) -> bool:
        statement = delete(NoteRow).where(
            NoteRow.id == note_id, NoteRow.owner_id == owner_id
        )
        return await self._changed_one(statement)

    async def _changed_one(self, statement: Any) -> bool:
        """Run an UPDATE or a DELETE: True if it touched exactly one row."""
        result = cast(CursorResult[Any], await self._session.execute(statement))
        return result.rowcount == 1
