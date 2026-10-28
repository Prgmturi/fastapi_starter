from typing import Protocol, runtime_checkable
from uuid import UUID

from fastapi_starter.features.notes.domain.note import Note


@runtime_checkable
class NoteRepository(Protocol):
    """Where the notes are kept: the port of the business layer.

    Every method takes the owner: for its caller a note of another user does
    not exist, so it is never found, changed or deleted.
    persistence/repository.py implements this port with SQLAlchemy.
    """

    async def page(self, owner_id: str, limit: int, offset: int) -> list[Note]:
        """One page of the owner's notes, the oldest first."""
        ...

    async def get(self, owner_id: str, note_id: UUID) -> Note | None:
        """The note, or None if it is missing or not the owner's."""
        ...

    async def add(self, note: Note) -> None:
        """Keep a new note."""
        ...

    async def save(self, note: Note) -> bool:
        """Store the changes of a note; False if it is no longer there."""
        ...

    async def delete(self, owner_id: str, note_id: UUID) -> bool:
        """Delete the note; False if it is missing or not the owner's."""
        ...
