from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NoteResponse(BaseModel):
    """A note as the API returns it. No owner: the caller is the owner.

    from_attributes reads the fields of the domain's Note, so a route
    returns NoteResponse.model_validate(note).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    body: str
    created_at: datetime
    updated_at: datetime
