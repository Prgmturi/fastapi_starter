"""Notes on a real Postgres — through HTTP, read back from the table.

Module under test: src/fastapi_starter/features/notes/
Layer: FastAPI integration, real database (the schema of the migrations)

WHY: tests/features/notes/ proves the rules on a repository in memory, and
the SQL by reading it. Here the SQL runs: the owner filter, the order, the
UUID and the times with their time zone go into Postgres and come back.
"""

from collections.abc import AsyncGenerator, Callable
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from fastapi_starter.core.auth.dependencies import get_current_user
from fastapi_starter.core.auth.schemas import RoleEnum, User
from fastapi_starter.core.database import DatabaseManager
from fastapi_starter.features.notes.persistence.models import NoteRow
from tests.test_exception_handlers import assert_problem

OTHER_USER = User(
    id="0b5d4e1c-9f3a-4c2e-8d7b-6a1f2e3d4c5b",
    username="other_user",
    roles=[RoleEnum.USER],
)


@pytest.fixture(autouse=True)
async def empty_notes(migrated_database, db_manager) -> None:
    """The notes table of the migrations, with no row."""
    async with db_manager.engine.begin() as connection:
        await connection.execute(text("DELETE FROM notes"))


@pytest.fixture
def notes_app(app, sample_user):
    """The app on the test database; the requests come from sample_user."""
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


async def stored(db_manager: DatabaseManager) -> list[NoteRow]:
    """The rows of the table, read in a session of their own."""
    async with db_manager.session_factory() as session:
        rows = await session.scalars(select(NoteRow).order_by(NoteRow.created_at))
        return list(rows)


class TestOnPostgres:
    async def test_create_stores_the_note(self, client, db_manager, sample_user):
        """[HP] 201, and the row has the id, the owner and UTC times."""
        response = await client.post(
            "/notes", json={"title": "Groceries", "body": "milk"}
        )

        assert response.status_code == 201
        [row] = await stored(db_manager)
        assert row.id == UUID(response.json()["id"])
        assert row.owner_id == sample_user.id
        assert (row.title, row.body) == ("Groceries", "milk")
        assert row.created_at.utcoffset().total_seconds() == 0

    async def test_the_note_comes_back_the_same(self, client):
        """[HP] What GET returns is what POST returned: times included."""
        created = (await client.post("/notes", json={"title": "Groceries"})).json()

        fetched = await client.get(f"/notes/{created['id']}")

        assert fetched.json() == created

    async def test_pages_in_creation_order(self, client):
        """[HP] Three notes, pages of one: the order they were created."""
        ids = [
            (await client.post("/notes", json={"title": str(n)})).json()["id"]
            for n in range(3)
        ]

        pages = [
            (await client.get("/notes", params={"limit": 1, "offset": n})).json()
            for n in range(3)
        ]

        assert [page[0]["id"] for page in pages] == ids

    async def test_update_moves_updated_at(self, client, db_manager):
        """[HP] PATCH changes the row: new title, same created_at, later updated_at."""
        created = (await client.post("/notes", json={"title": "Groceries"})).json()

        await client.patch(f"/notes/{created['id']}", json={"title": "Shopping"})

        [row] = await stored(db_manager)
        assert row.title == "Shopping"
        assert row.updated_at > row.created_at

    async def test_delete_removes_the_row(self, client, db_manager):
        """[HP] DELETE, then the table is empty and GET answers 404."""
        created = (await client.post("/notes", json={"title": "Groceries"})).json()

        response = await client.delete(f"/notes/{created['id']}")

        assert response.status_code == 204
        assert await stored(db_manager) == []
        assert_problem(await client.get(f"/notes/{created['id']}"), 404)


class TestOwnersOnPostgres:
    """The owner filter of the SQL, on the real table.

    WHY: a query without "AND owner_id = ..." would hand a note to anyone
    who knows its id. The unit tests read the SQL; here it runs.
    """

    async def test_another_user_reaches_nothing(self, client, log_in, db_manager):
        """[SEC] get, change, delete and list -> 404 or empty; the row stays."""
        created = (
            await client.post("/notes", json={"title": "Groceries", "body": "milk"})
        ).json()

        log_in(OTHER_USER)

        assert_problem(await client.get(f"/notes/{created['id']}"), 404)
        assert_problem(
            await client.patch(f"/notes/{created['id']}", json={"title": "x"}), 404
        )
        assert_problem(await client.delete(f"/notes/{created['id']}"), 404)
        assert (await client.get("/notes")).json() == []
        [row] = await stored(db_manager)
        assert (row.title, row.body) == ("Groceries", "milk")
