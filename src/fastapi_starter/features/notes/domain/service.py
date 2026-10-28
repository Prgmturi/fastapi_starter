from uuid import UUID

from fastapi_starter.core.exceptions import NotFoundError
from fastapi_starter.features.notes.domain.note import Note
from fastapi_starter.features.notes.domain.protocols import NoteRepository


class NoteService:
    """The rules on notes: each user reaches only their own.

    A note of another user gets the answer of a note that does not exist,
    NotFoundError, so no one learns which ids are taken.
    """

    def __init__(self, repository: NoteRepository) -> None:
        self._repository = repository

    async def list_notes(self, owner_id: str, limit: int, offset: int) -> list[Note]:
        return await self._repository.page(owner_id, limit, offset)

    async def create_note(self, owner_id: str, title: str, body: str) -> Note:
        note = Note.create(owner_id, title, body)
        await self._repository.add(note)
        return note

    async def get_note(self, owner_id: str, note_id: UUID) -> Note:
        """Raises NotFoundError if the note is missing or not the owner's."""
        note = await self._repository.get(owner_id, note_id)
        if note is None:
            raise NotFoundError("Note", str(note_id))
        return note

    async def update_note(
        self,
        owner_id: str,
        note_id: UUID,
        title: str | None = None,
        body: str | None = None,
    ) -> Note:
        """Change the fields given. Raises NotFoundError as get_note does."""
        note = (await self.get_note(owner_id, note_id)).edit(title, body)
        # Deleted by another request between the read and the write
        if not await self._repository.save(note):
            raise NotFoundError("Note", str(note_id))
        return note

    async def delete_note(self, owner_id: str, note_id: UUID) -> None:
        """Raises NotFoundError if the note is missing or not the owner's."""
        if not await self._repository.delete(owner_id, note_id):
            raise NotFoundError("Note", str(note_id))
