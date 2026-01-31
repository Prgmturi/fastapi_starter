"""Database-specific fixtures: mock session, mock manager, test repository."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Column, Integer, String

from fastapi_starter.core.database.manager import Base
from fastapi_starter.core.database.repository import BaseRepository

# ---------------------------------------------------------------------------
# Inline test model and repository (never leaves test scope)
# ---------------------------------------------------------------------------


class FakeModel(Base):
    """Minimal SQLAlchemy model for testing BaseRepository."""

    __tablename__ = "fake_model"
    id = Column(Integer, primary_key=True)
    name = Column(String)


class FakeRepository(BaseRepository[FakeModel]):
    """Concrete subclass for testing BaseRepository CRUD."""

    model = FakeModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """AsyncMock of SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_db_manager():
    """AsyncMock of DatabaseManager (concrete, for unit testing manager itself)."""
    mock = AsyncMock()
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()
    mock.health_check = AsyncMock(return_value=True)
    mock.session_factory = MagicMock()
    return mock


@pytest.fixture
def test_repository(mock_session) -> FakeRepository:
    """FakeRepository wired with a mock session for CRUD tests."""
    return FakeRepository(mock_session)
