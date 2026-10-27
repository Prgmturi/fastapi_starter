from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Self
from uuid import UUID, uuid4

# What a note may hold. The request schemas and the table take these too.
TITLE_MAX_LENGTH = 200
BODY_MAX_LENGTH = 10_000


@dataclass(frozen=True)
class Note:
    """A note of one user.

    The domain decides the id and the times, and persistence only stores
    them: nothing has to be read back from the database after a save.
    """

    id: UUID
    owner_id: str
    title: str
    body: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, owner_id: str, title: str, body: str) -> Self:
        """A new note of owner_id, created now."""
        now = datetime.now(UTC)
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            title=title,
            body=body,
            created_at=now,
            updated_at=now,
        )

    def edit(self, title: str | None = None, body: str | None = None) -> Self:
        """A copy with the fields given changed, and updated_at now."""
        return replace(
            self,
            title=self.title if title is None else title,
            body=self.body if body is None else body,
            updated_at=datetime.now(UTC),
        )
