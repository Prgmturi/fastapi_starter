from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fastapi_starter.features.notes.domain.note import (
    BODY_MAX_LENGTH,
    TITLE_MAX_LENGTH,
)


class NoteCreate(BaseModel):
    """A new note. The id, the owner and the times are the server's.

    A field the API does not know is refused with 422 instead of ignored: a
    client that sends owner_id learns that it cannot choose it.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    body: str = Field(default="", max_length=BODY_MAX_LENGTH)


class NoteUpdate(BaseModel):
    """The fields to change; the others stay as they are."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX_LENGTH)
    body: str | None = Field(default=None, max_length=BODY_MAX_LENGTH)

    @model_validator(mode="after")
    def changes_something(self) -> Self:
        if self.title is None and self.body is None:
            raise ValueError("give the title, the body or both")
        return self
