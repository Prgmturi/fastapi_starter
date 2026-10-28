"""Tests for the wiring of notes — the service of a request.

Module under test: src/fastapi_starter/features/notes/api/dependencies.py
Layer: HTTP wiring (mock session)

WHY this test exists: the other tests replace get_note_service, so without
this one a service built on the wrong repository, or on no session, would
pass them all.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi_starter.features.notes.api.dependencies import get_note_service
from fastapi_starter.features.notes.domain.service import NoteService
from tests.features.notes.conftest import OWNER


async def test_the_service_reads_through_the_session():
    """[HP] A NoteService whose repository queries the request's session."""
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []

    service = get_note_service(session)

    assert isinstance(service, NoteService)
    assert await service.list_notes(OWNER, limit=5, offset=0) == []
    session.execute.assert_awaited_once()
