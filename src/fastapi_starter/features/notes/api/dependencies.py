from typing import Annotated

from fastapi import Depends

from fastapi_starter.core.database import DbSession
from fastapi_starter.features.notes.domain.protocols import NoteRepository
from fastapi_starter.features.notes.domain.service import NoteService
from fastapi_starter.features.notes.persistence.repository import SqlNoteRepository


def get_note_service(session: DbSession) -> NoteService:
    """The service of one request, on the session of the request.

    The repository passes through a variable typed as the port, so mypy
    checks that SqlNoteRepository still matches NoteRepository.
    """
    repository: NoteRepository = SqlNoteRepository(session)
    return NoteService(repository)


NoteServiceDep = Annotated[NoteService, Depends(get_note_service)]
