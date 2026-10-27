from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_starter.core.database import Base
from fastapi_starter.features.notes.domain.note import TITLE_MAX_LENGTH


class NoteRow(Base):
    """The notes table.

    The business layer never sees this class: the repository turns each row
    into a Note. alembic/env.py finds it because the module is called models.
    """

    __tablename__ = "notes"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    # The sub claim of the token: the id of the user in Keycloak
    owner_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
