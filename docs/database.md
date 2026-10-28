# Database

PostgreSQL, reached with SQLAlchemy 2 in async mode, and Alembic for the migrations. Why SQLAlchemy is part of `core` and not an adapter: [decision record 0005](adr/0005-database.md).

## One session for each request

`DbSession` gives a route one session and one transaction:

- it commits when the route returns, before the response is sent;
- it rolls back when anything fails.

So a failed commit answers 500, never 201.

## Repositories

A repository extends `BaseRepository`, which has `get_by_id`, `get_page`, `create` and `delete`:

```python
from typing import Annotated

from fastapi import Query

from fastapi_starter.core.database import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    BaseRepository,
    DbSession,
)


class ProductRepository(BaseRepository[Product]):
    model = Product


@router.get("/", response_model=list[ProductOut])
async def list_products(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await ProductRepository(db).get_page(limit=limit, offset=offset)
```

- `get_page` sorts by primary key, so a row updated between two pages is neither skipped nor shown twice. A row deleted from an earlier page still shifts the next pages by one: that is the limit of paging by offset.
- `get_page` refuses a `limit` above `MAX_PAGE_SIZE` (100). Bound the query parameter as above, and the client gets 422 instead of 500.

## A feature with rules of its own

The example feature, `features/notes/`, keeps SQLAlchemy in its `persistence/` layer, behind a port of its domain (`domain/protocols.py`). Its repository, `SqlNoteRepository`, writes its own queries: each one filters by owner, and each row becomes a `Note` of the domain. The domain stays in plain Python, and its rules are tested without a database. The layers are described in [the architecture guide](architecture.md).

## Work after the response

Background tasks and streaming responses run after `DbSession` has closed its session. Give them the database provider, and open a session there:

```python
from typing import Annotated

from fastapi import BackgroundTasks, Depends

from fastapi_starter.core.database import DatabaseProvider, get_db_manager


async def rebuild_catalog(db: DatabaseProvider) -> None:
    async with db.session_factory.begin() as session:  # commit at the end, rollback on error
        ...


@router.post("/catalog/rebuild", status_code=202)
async def start_rebuild(
    background: BackgroundTasks,
    db: Annotated[DatabaseProvider, Depends(get_db_manager)],
) -> None:
    background.add_task(rebuild_catalog, db)
```

## Migrations

```bash
uv run alembic upgrade head                                  # the database to the last migration
uv run alembic revision --autogenerate -m "add products table"
uv run alembic downgrade -1                                  # one migration back
```

- **Where models live.** Define a model by subclassing `Base` from `core/database/base.py`, in a module called `models` under `features/`: `features/<name>/models.py`, or, as in the example, `features/notes/persistence/models.py`. `alembic/env.py` imports every such module, at any depth (`core/database/migrations.py`), so no model is left out of a migration.
- **No model at all.** `--autogenerate` then stops with an explanation, instead of writing a migration that drops every table of the database.
- **Read it first.** Read the file Alembic writes in `alembic/versions/` before you commit it, and let ruff tidy it (`uv run ruff format`).
- **Only `DATABASE_*`.** Migrations read no other setting, so they run before a new version starts, without the rest of the configuration. In `compose.yaml` the `migrate` service runs `alembic upgrade head` from the image of the app, and the API starts only after it succeeds.
- **CI.** It runs every migration up to the last one, compares the result with the models (`alembic check`: a model changed without its migration fails the build), then goes down to the start and up again.

### Names of indexes and constraints

They come from the naming convention of `core/database/base.py`: `pk_<table>`, `uq_<table>_<columns>`, `ix_<table>_<columns>`, `fk_<table>_<columns>_<referred table>`. Without it Postgres would pick its own names, and the downgrades Alembic writes could not drop them.

A `CheckConstraint` needs a `name=`, which becomes `ck_<table>_<name>`; without it the model fails at import. The convention is fixed since the first migration: changing it now renames constraints that exist.

## The connection pool

The pool settings have bounds in every environment, because SQLAlchemy reads some values in a surprising way:

| Setting | Bound | Why |
|---|---|---|
| `DATABASE_POOL_SIZE` | at least 1 | 0 means no limit |
| `DATABASE_POOL_MAX_OVERFLOW` | at least 0 | -1 means no limit |
| `DATABASE_POOL_TIMEOUT`, `DATABASE_POOL_RECYCLE` | above 0 | `DATABASE_POOL_RECYCLE=0` opens a new connection for every query |
| `DATABASE_CONNECT_TIMEOUT`, `DATABASE_COMMAND_TIMEOUT` | above 0 | seconds to connect, and seconds a query may run: a slower query answers 500 |

A value out of range stops the startup, with an error that names the variable. `DATABASE_ECHO=true` writes every query to the logs with its values, so production refuses it.
