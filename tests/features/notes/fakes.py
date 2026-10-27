"""A NoteRepository kept in memory, for the tests of the domain and the API."""

from uuid import UUID

from fastapi_starter.features.notes.domain.note import Note


class InMemoryNoteRepository:
    """The port of notes on a dict: what the domain needs, with no database.

    It keeps the rules of the port: every method filters by owner, and a
    page is ordered by created_at, then id.
    """

    def __init__(self) -> None:
        self.notes: dict[UUID, Note] = {}

    async def page(self, owner_id: str, limit: int, offset: int) -> list[Note]:
        own = [note for note in self.notes.values() if note.owner_id == owner_id]
        own.sort(key=lambda note: (note.created_at, note.id))
        return own[offset : offset + limit]

    async def get(self, owner_id: str, note_id: UUID) -> Note | None:
        note = self.notes.get(note_id)
        return note if note is not None and note.owner_id == owner_id else None

    async def add(self, note: Note) -> None:
        self.notes[note.id] = note

    async def save(self, note: Note) -> bool:
        if await self.get(note.owner_id, note.id) is None:
            return False
        self.notes[note.id] = note
        return True

    async def delete(self, owner_id: str, note_id: UUID) -> bool:
        if await self.get(owner_id, note_id) is None:
            return False
        del self.notes[note_id]
        return True
