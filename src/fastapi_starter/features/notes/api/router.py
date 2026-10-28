from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from fastapi_starter.core.auth import CurrentUser
from fastapi_starter.core.database import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from fastapi_starter.features.notes.api.dependencies import NoteServiceDep
from fastapi_starter.features.notes.api.schemas.request.note import (
    NoteCreate,
    NoteUpdate,
)
from fastapi_starter.features.notes.api.schemas.response.note import NoteResponse

notes_router = APIRouter(prefix="/notes", tags=["Notes"])


@notes_router.get("", summary="List my notes")
async def list_notes(
    user: CurrentUser,
    service: NoteServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NoteResponse]:
    """The notes of the caller, the oldest first, one page at a time."""
    notes = await service.list_notes(user.id, limit, offset)
    return [NoteResponse.model_validate(note) for note in notes]


@notes_router.post("", status_code=status.HTTP_201_CREATED, summary="Create a note")
async def create_note(
    payload: NoteCreate,
    user: CurrentUser,
    service: NoteServiceDep,
    request: Request,
    response: Response,
) -> NoteResponse:
    """A new note of the caller. Location gives its address."""
    note = await service.create_note(user.id, payload.title, payload.body)
    response.headers["Location"] = request.app.url_path_for(
        "get_note", note_id=str(note.id)
    )
    return NoteResponse.model_validate(note)


@notes_router.get("/{note_id}", summary="Get a note")
async def get_note(
    note_id: UUID, user: CurrentUser, service: NoteServiceDep
) -> NoteResponse:
    """One note of the caller; 404 for a note of another user."""
    return NoteResponse.model_validate(await service.get_note(user.id, note_id))


@notes_router.patch("/{note_id}", summary="Change a note")
async def update_note(
    note_id: UUID, payload: NoteUpdate, user: CurrentUser, service: NoteServiceDep
) -> NoteResponse:
    """Change the title, the body or both."""
    note = await service.update_note(user.id, note_id, payload.title, payload.body)
    return NoteResponse.model_validate(note)


@notes_router.delete(
    "/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a note"
)
async def delete_note(
    note_id: UUID, user: CurrentUser, service: NoteServiceDep
) -> None:
    """Delete a note of the caller."""
    await service.delete_note(user.id, note_id)
