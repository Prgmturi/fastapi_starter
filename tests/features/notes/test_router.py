"""Tests for the HTTP layer of notes — status codes, schemas, owners.

Module under test: src/fastapi_starter/features/notes/api/
Layer: HTTP (the real routes and service, the in-memory repository)

WHY these tests exist: the API is the contract with the frontend. A note of
another user must answer 404 like a missing one, a client must not choose
the owner, and the response must not carry it.
"""

from collections.abc import AsyncGenerator, Callable
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi_starter.core.auth.dependencies import get_current_user
from fastapi_starter.core.auth.schemas import User
from fastapi_starter.core.database import MAX_PAGE_SIZE
from fastapi_starter.features.notes.api.dependencies import get_note_service
from fastapi_starter.features.notes.domain.note import TITLE_MAX_LENGTH
from tests.test_exception_handlers import assert_problem


@pytest.fixture
def notes_app(app, service, sample_user):
    """The app with the notes service on the in-memory repository.

    The requests come from sample_user, until a test calls log_in.
    """
    app.dependency_overrides[get_note_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: sample_user
    return app


@pytest.fixture
async def client(notes_app) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=notes_app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest.fixture
def log_in(notes_app) -> Callable[[User], None]:
    """Make the next requests come from another user."""

    def as_user(user: User) -> None:
        notes_app.dependency_overrides[get_current_user] = lambda: user

    return as_user


async def create(client: AsyncClient, title: str = "Groceries", body: str = "milk"):
    response = await client.post("/notes", json={"title": title, "body": body})
    assert response.status_code == 201, response.text
    return response.json()


class TestCreate:
    async def test_201_with_location_and_the_note(self, client):
        """[HP] 201, Location of the new note, and the note without its owner."""
        response = await client.post(
            "/notes", json={"title": "Groceries", "body": "milk"}
        )

        assert response.status_code == 201
        note = response.json()
        assert response.headers["location"] == f"/notes/{note['id']}"
        assert set(note) == {"id", "title", "body", "created_at", "updated_at"}
        assert (note["title"], note["body"]) == ("Groceries", "milk")

    async def test_body_may_be_left_out(self, client):
        """[HP] A note with a title only has an empty body."""
        response = await client.post("/notes", json={"title": "Groceries"})

        assert response.json()["body"] == ""

    @pytest.mark.parametrize(
        "payload",
        [
            {"title": ""},
            {"title": "x" * (TITLE_MAX_LENGTH + 1)},
            {"body": "no title"},
        ],
        ids=["empty-title", "title-too-long", "no-title"],
    )
    async def test_invalid_note_refused(self, client, payload):
        """[EC] A title out of 1..TITLE_MAX_LENGTH, or none -> 422."""
        response = await client.post("/notes", json=payload)

        assert_problem(response, 422)

    async def test_the_owner_cannot_be_chosen(self, client):
        """[SEC] owner_id in the body -> 422, not a note of someone else."""
        response = await client.post(
            "/notes", json={"title": "Groceries", "owner_id": "someone-else"}
        )

        assert_problem(response, 422)


class TestList:
    async def test_own_notes_oldest_first(self, client):
        """[HP] The caller's notes, in the order they were created."""
        first = await create(client, "first")
        second = await create(client, "second")

        response = await client.get("/notes")

        assert response.status_code == 200
        assert [note["id"] for note in response.json()] == [first["id"], second["id"]]

    async def test_one_page(self, client):
        """[HP] limit and offset pick the page."""
        notes = [await create(client, str(n)) for n in range(3)]

        response = await client.get("/notes", params={"limit": 1, "offset": 1})

        assert [note["id"] for note in response.json()] == [notes[1]["id"]]

    @pytest.mark.parametrize(
        "params",
        [{"limit": 0}, {"limit": MAX_PAGE_SIZE + 1}, {"offset": -1}],
        ids=["empty-page", "page-too-large", "negative-offset"],
    )
    async def test_page_out_of_range_refused(self, client, params):
        """[EC] A page the repository would refuse -> 422, not 500."""
        response = await client.get("/notes", params=params)

        assert_problem(response, 422)


class TestGet:
    async def test_own_note(self, client):
        """[HP] 200 and the note."""
        note = await create(client)

        response = await client.get(f"/notes/{note['id']}")

        assert response.status_code == 200
        assert response.json() == note

    async def test_missing_note(self, client):
        """[EC] An id nobody has -> 404 problem."""
        response = await client.get(f"/notes/{uuid4()}")

        assert_problem(response, 404)

    async def test_not_a_uuid(self, client):
        """[EC] An id that is not a UUID -> 422 before the service runs."""
        response = await client.get("/notes/42")

        assert_problem(response, 422)


class TestUpdate:
    async def test_title_only(self, client):
        """[HP] PATCH with a title keeps the body and moves updated_at."""
        note = await create(client)

        response = await client.patch(f"/notes/{note['id']}", json={"title": "Shop"})

        assert response.status_code == 200
        updated = response.json()
        assert (updated["title"], updated["body"]) == ("Shop", "milk")
        assert updated["created_at"] == note["created_at"]
        assert updated["updated_at"] >= note["updated_at"]

    async def test_nothing_to_change_refused(self, client):
        """[EC] An empty PATCH -> 422: the client probably sent the wrong body."""
        note = await create(client)

        response = await client.patch(f"/notes/{note['id']}", json={})

        assert_problem(response, 422)


class TestDelete:
    async def test_204_then_gone(self, client):
        """[HP] 204 with no body, then the note is not found."""
        note = await create(client)

        response = await client.delete(f"/notes/{note['id']}")

        assert response.status_code == 204
        assert response.content == b""
        assert_problem(await client.get(f"/notes/{note['id']}"), 404)


class TestOwners:
    """Two users, one note.

    WHY: each user reaches only their own notes, and a note of another user
    answers like a missing one, so no one learns which ids exist.
    """

    async def test_another_user_reaches_nothing(self, client, log_in, other_user):
        """[SEC] get, change and delete -> 404; the list is empty."""
        note = await create(client)

        log_in(other_user)

        assert_problem(await client.get(f"/notes/{note['id']}"), 404)
        assert_problem(
            await client.patch(f"/notes/{note['id']}", json={"title": "x"}), 404
        )
        assert_problem(await client.delete(f"/notes/{note['id']}"), 404)
        assert (await client.get("/notes")).json() == []

    async def test_the_owner_still_has_it(
        self, client, log_in, other_user, sample_user
    ):
        """[SEC] After the attempts of the other user the note is unchanged."""
        note = await create(client)
        log_in(other_user)
        await client.patch(f"/notes/{note['id']}", json={"title": "x"})
        await client.delete(f"/notes/{note['id']}")

        log_in(sample_user)

        assert (await client.get(f"/notes/{note['id']}")).json() == note


class TestNeedsLogin:
    async def test_no_token_401(self, app):
        """[SEC] Without a token every route answers 401."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as anonymous:
            response = await anonymous.get("/notes")

        assert_problem(response, 401)
