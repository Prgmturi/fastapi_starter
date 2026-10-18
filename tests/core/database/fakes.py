"""Fake model and repository for the BaseRepository tests.

A normal module, not conftest.py: test files import these classes at the
top, like any other module. pytest does not want conftest.py imported.
"""

from sqlalchemy import Column, Integer, String

from fastapi_starter.core.database.manager import Base
from fastapi_starter.core.database.repository import BaseRepository


class FakeModel(Base):
    """Minimal SQLAlchemy model for testing BaseRepository."""

    __tablename__ = "fake_model"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class FakeRepository(BaseRepository[FakeModel]):
    """Concrete subclass for testing BaseRepository CRUD."""

    model = FakeModel
