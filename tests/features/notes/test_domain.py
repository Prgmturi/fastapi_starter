"""Tests for the business layer of notes — the Note and the rules.

Module under test: src/fastapi_starter/features/notes/domain/
Layer: Pure domain (an in-memory repository, no HTTP, no database)

WHY these tests exist: the rule of the feature is that each user reaches
only their own notes, and a note of another user must look exactly like a
note that does not exist. Here the rule runs on its own, in milliseconds.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC
from uuid import UUID, uuid4

import pytest

from fastapi_starter.core.exceptions import NotFoundError
from fastapi_starter.features.notes.domain.note import Note
from tests.features.notes.conftest import OWNER

OTHER = "someone-else"


class TestNote:
    def test_create_sets_id_owner_and_times(self):
        """[HP] A new note: a random UUID, its owner, created and updated now."""
        note = Note.create(OWNER, "Groceries", "milk")

        assert isinstance(note.id, UUID)
        assert note.id.version == 4
        assert (note.owner_id, note.title, note.body) == (OWNER, "Groceries", "milk")
        assert note.created_at == note.updated_at
        assert note.created_at.tzinfo is UTC

    def test_two_notes_get_two_ids(self):
        """[EC] The id is not derived from the content."""
        assert Note.create(OWNER, "a", "").id != Note.create(OWNER, "a", "").id

    def test_edit_changes_only_the_fields_given(self):
        """[HP] A new title keeps the body, the id and created_at."""
        note = Note.create(OWNER, "Groceries", "milk")

        edited = note.edit(title="Shopping")

        assert (edited.title, edited.body) == ("Shopping", "milk")
        assert (edited.id, edited.created_at) == (note.id, note.created_at)
        assert edited.updated_at >= note.updated_at

    def test_edit_leaves_the_original_alone(self):
        """[HP] edit returns a copy: the note the caller holds does not change."""
        note = Note.create(OWNER, "Groceries", "milk")

        note.edit(body="eggs")

        assert note.body == "milk"

    def test_a_note_cannot_be_changed_in_place(self):
        """[EC] Frozen: a change goes through edit, which moves updated_at."""
        note = Note.create(OWNER, "Groceries", "milk")

        with pytest.raises(FrozenInstanceError):
            note.title = "Shopping"


class TestListNotes:
    async def test_only_the_owners_notes_oldest_first(self, service):
        """[HP] Another user's notes are not listed; the order is creation."""
        first = await service.create_note(OWNER, "first", "")
        await service.create_note(OTHER, "not mine", "")
        second = await service.create_note(OWNER, "second", "")

        assert await service.list_notes(OWNER, limit=10, offset=0) == [first, second]

    async def test_one_page_at_a_time(self, service):
        """[HP] limit and offset pick the page."""
        notes = [await service.create_note(OWNER, str(n), "") for n in range(5)]

        assert await service.list_notes(OWNER, limit=2, offset=2) == notes[2:4]


class TestCreateNote:
    async def test_the_note_is_kept(self, service, repository):
        """[HP] create_note returns the note it handed to the repository."""
        note = await service.create_note(OWNER, "Groceries", "milk")

        assert repository.notes == {note.id: note}


class TestGetNote:
    async def test_own_note(self, service):
        """[HP] The owner gets the note."""
        note = await service.create_note(OWNER, "Groceries", "milk")

        assert await service.get_note(OWNER, note.id) == note

    async def test_missing_note(self, service):
        """[EC] An id nobody has -> NotFoundError."""
        with pytest.raises(NotFoundError):
            await service.get_note(OWNER, uuid4())

    async def test_another_users_note_is_not_found(self, service):
        """[SEC] The note of another user -> the same NotFoundError.

        WHY: a 403 would tell the caller that the id exists.
        """
        note = await service.create_note(OTHER, "not mine", "")

        with pytest.raises(NotFoundError) as exc_info:
            await service.get_note(OWNER, note.id)

        assert exc_info.value.message == f"Note with id '{note.id}' not found"


class TestUpdateNote:
    async def test_the_change_is_saved(self, service, repository):
        """[HP] The new title is kept, the body stays."""
        note = await service.create_note(OWNER, "Groceries", "milk")

        updated = await service.update_note(OWNER, note.id, title="Shopping")

        assert repository.notes[note.id] == updated
        assert (updated.title, updated.body) == ("Shopping", "milk")

    async def test_another_users_note_stays_as_it_is(self, service, repository):
        """[SEC] Changing a note of another user -> NotFoundError, no change."""
        note = await service.create_note(OTHER, "not mine", "")

        with pytest.raises(NotFoundError):
            await service.update_note(OWNER, note.id, title="mine now")

        assert repository.notes[note.id] == note

    async def test_deleted_between_read_and_write(self, service, repository):
        """[EC] The note goes away after it was read -> NotFoundError.

        WHY: another request of the same user can delete it in between;
        the save finds no row, and the client must not get 200.
        """
        note = await service.create_note(OWNER, "Groceries", "milk")

        async def gone(_note):
            return False

        repository.save = gone

        with pytest.raises(NotFoundError):
            await service.update_note(OWNER, note.id, body="eggs")


class TestDeleteNote:
    async def test_own_note_is_deleted(self, service, repository):
        """[HP] The owner deletes the note."""
        note = await service.create_note(OWNER, "Groceries", "milk")

        await service.delete_note(OWNER, note.id)

        assert repository.notes == {}

    async def test_another_users_note_stays(self, service, repository):
        """[SEC] Deleting a note of another user -> NotFoundError, still there."""
        note = await service.create_note(OTHER, "not mine", "")

        with pytest.raises(NotFoundError):
            await service.delete_note(OWNER, note.id)

        assert note.id in repository.notes

    async def test_missing_note(self, service):
        """[EC] An id nobody has -> NotFoundError."""
        with pytest.raises(NotFoundError):
            await service.delete_note(OWNER, uuid4())
