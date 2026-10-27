"""Notes fixtures: the in-memory repository, the service, a second user."""

import pytest

from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.features.notes.domain.service import NoteService
from tests.features.notes.fakes import InMemoryNoteRepository

# The owner of the notes in these tests: sample_user of tests/conftest.py
OWNER = "e37e9825-ac1c-4bd3-8380-579af43eac4823"


@pytest.fixture
def repository() -> InMemoryNoteRepository:
    return InMemoryNoteRepository()


@pytest.fixture
def service(repository) -> NoteService:
    """The real service, on the in-memory repository."""
    return NoteService(repository)


@pytest.fixture
def other_user() -> User:
    """A second user, to check that notes stay their owner's."""
    return User(
        id="0b5d4e1c-9f3a-4c2e-8d7b-6a1f2e3d4c5b",
        username="other_user",
        roles=[RoleEnum.USER],
    )
