# fastapi-starter

![Python](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![CI](https://github.com/Prgmturi/fastapi_starter/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/Prgmturi/fastapi_starter)

A starting point for a backend in FastAPI, built to teach as much as to be used. Login, database, logs, errors, tests and deployment are already in place. You add features, and the structure shows you where each piece of code goes.

## What you get

- **Login** with Keycloak (OAuth 2.0 with PKCE). The API checks every token itself, and keeps the refresh token in a cookie that JavaScript cannot read.
- **An architecture CI enforces.** Three parts, `core`, `adapters` and `features`, and one rule: imports go down. A build fails when a module breaks it.
- **An example to copy**, `features/notes`, with its business rules in plain Python, tested without a database.
- **PostgreSQL** with async SQLAlchemy, and migrations that CI checks against the models.
- **One format for every error** (RFC 9457) and for every log line (JSON in production).
- **Tests at three levels:** unit tests, integration tests on a real Postgres, and a login through the whole stack.
- **Deployment:** a Docker image for every release, and a compose file for one server.

## Start in five minutes

You need Docker.

```bash
git clone https://github.com/Prgmturi/fastapi_starter.git
cd fastapi_starter
docker compose up --build --wait
```

That starts the whole stack, with development values: no `.env` to write.

| Service | Where | What it is |
|---|---|---|
| `api` | http://localhost:8000, its documentation at `/docs` | The app |
| `migrate` | | Brings the database to the last migration, then exits; the API starts after it |
| `db` | `localhost:5433` | The app's Postgres |
| `keycloak` | http://localhost:8080, user `admin`, password `admin` | The login server, with a test user: `testuser`, password `testuser-dev-password` |
| `keycloak-db` | | Keycloak's Postgres |

To see a whole login work, install [uv](https://docs.astral.sh/uv/) and run `uv run pytest -m e2e`: it logs `testuser` in through Keycloak, calls the API with the token, and writes and deletes a note.

## How it is built

### One request, from start to end

```
HTTP request: POST /notes
   │
   ▼
features/notes/api/router.py        reads the request (schemas/request), answers (schemas/response)
   │   before the route runs, CurrentUser checks the token through a port:
   │   adapters/keycloak/ verifies it with the keys of Keycloak
   ▼
features/notes/domain/service.py    the rules: create the note for this user
   │   through a port, domain/protocols.py
   ▼
features/notes/persistence/         the SQL, in the transaction of the request
   │
   ▼
PostgreSQL
```

### Three parts, one rule

| Folder | What lives there |
|---|---|
| `core/` | What every feature needs: the ports, the auth logic, the database, the settings, the logs, the errors |
| `adapters/` | The code that talks to a service outside the app, one folder for each: `keycloak/` |
| `features/` | What the API does: your endpoints |

The rule: **a module imports only from the parts below its own.** The entry points (`main.py`, `serve.py`, `healthcheck.py`) are at the top. Below them sits `bootstrap.py`, then `features/` and `adapters/`, then `core/`. Features and adapters never import each other: a feature asks for a port, and `bootstrap.py` hands it the adapter. CI checks the rule on every push.

### Words used here

| Word | What it means here | Example |
|---|---|---|
| Port | A `Protocol` class: what a service must be able to do, with no code that does it | `OAuthProvider` |
| Adapter | A class that does it, with a real library or service | `KeycloakClient` |
| Domain | The rules of a feature, in plain Python: no FastAPI, no SQL | `features/notes/domain/` |
| `bootstrap.py` | The one place that builds the adapters and hands them to the app | |
| Entry point | A module started from outside the code | `serve.py`, the command of the image |

More in [the architecture guide](docs/architecture.md), and the reasons behind each choice in [the decision records](docs/adr/README.md).

## Your first feature

Copy `features/notes`. It has three layers, and each one imports only the layers below it:

| Layer | What it holds |
|---|---|
| `api/` | The routes, and what the client sends (`schemas/request/`) and gets back (`schemas/response/`) |
| `persistence/` | The table, and the repository that does the SQL |
| `domain/` | The rules, in plain Python, and the port the repository implements |

To add `tasks`:

1. **Copy the example and its tests:**

   ```bash
   cp -r src/fastapi_starter/features/notes src/fastapi_starter/features/tasks
   cp -r tests/features/notes tests/features/tasks
   cp tests/integration/test_notes.py tests/integration/test_tasks.py
   ```

   Then rename `notes` and `note` inside the copies, in the names of the files too: the three `note.py` become `task.py`.
2. **Register the router** in `create_app()` of `main.py`: import `tasks_router` from `fastapi_starter.features.tasks.api.router`, and add `app.include_router(tasks_router)` after the others.
3. **Add the feature to its contract:** put `"fastapi_starter.features.tasks"` in the `containers` of the contract "Inside a feature", in `pyproject.toml`.
4. **Write the migration.** Alembic finds the new table by itself:

   ```bash
   uv run alembic revision --autogenerate -m "create tasks table"
   uv run alembic upgrade head
   ```

   Read the file it writes in `alembic/versions/` before you commit it.
5. **Tidy and check.** `uv run ruff check --fix` and `uv run ruff format`: the new names change the order of some imports, and Alembic writes in its own style. Then `uv run pytest`, `uv run pytest -m integration`, `uv run mypy src/` and `uv run lint-imports`.

Keep the rules of the example: the owner comes from the token, never from the body; every query filters by owner; a note of another user answers 404, like a missing one. A feature with no rules of its own can stay flat, as `features/auth` is. Both are explained in [the architecture guide](docs/architecture.md#the-example-feature).

## Everyday tasks

### Protect a route

```python
from fastapi_starter.core.auth.dependencies import AdminUser, CurrentUser


@router.get("/profile")
async def profile(user: CurrentUser): ...  # any user who is logged in


@router.get("/stats")
async def stats(user: AdminUser): ...  # admin or superadmin
```

Without a token the route answers 401, and without the role 403. Roles, and how a login works: [the authentication guide](docs/authentication.md).

### Return an error

```python
from fastapi_starter.core.exceptions import NotFoundError

raise NotFoundError("Note", note_id)  # 404, with a body the client can read
```

Every error is a problem document (RFC 9457): [the operations guide](docs/operations.md#errors).

### Read and write the database

The simple way, for a feature with no rules of its own:

```python
from fastapi_starter.core.database import BaseRepository, DbSession
from fastapi_starter.core.exceptions import NotFoundError


class ProductRepository(BaseRepository[Product]):
    model = Product


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int, db: DbSession):
    product = await ProductRepository(db).get_by_id(product_id)
    if product is None:
        raise NotFoundError("Product", product_id)
    return product
```

`Product` is your model, on `Base`, and `ProductResponse` the schema of the answer: only its fields leave the API. `DbSession` opens one transaction for each request, and commits it before the response leaves. Pages, background work, migrations: [the database guide](docs/database.md).

### Change the database

Change a model, then:

```bash
uv run alembic revision --autogenerate -m "what changes"
uv run alembic upgrade head
```

CI fails when a model changes without its migration.

### Run the tests

```bash
uv run pytest                  # the unit tests: no database, no Keycloak
uv run pytest -m integration   # on a real Postgres
uv run pytest -m e2e           # a login through the running stack
```

The integration tests need a database whose name ends in `_test`, created once: `docker compose exec db createdb -U appbase appbase_test`. More in [the development guide](docs/development.md).

### Run the app on your machine

```bash
uv sync
uv run pre-commit install         # ruff, gitleaks and commitlint on every commit
cp .env.example .env
docker compose up --wait db keycloak
uv run alembic upgrade head
uv run uvicorn fastapi_starter.main:create_app --factory --reload
```

## Configuration

Settings come from environment variables, or from `.env` in the root of the repository. `.env.example` lists them all, each with a comment. With `APP_ENVIRONMENT=production` the app refuses to start while a development value is left, and names it. Every setting: [the operations guide](docs/operations.md#settings).

## Production

`compose.prod.yaml`, over `compose.yaml`, runs the stack on one server: the image of a release, Keycloak behind a TLS proxy, every secret from the server's `.env`. [The production guide](docs/production.md) goes from the first start to the backups, with a checklist before going live.

## Learn more

| Guide | Read it to |
|---|---|
| [Architecture](docs/architecture.md) | Understand the parts, the layers of a feature, and what CI checks |
| [Authentication](docs/authentication.md) | Follow a login, set up Keycloak, use roles |
| [Database](docs/database.md) | Use sessions, pages, background work and migrations |
| [Operations](docs/operations.md) | Read errors, health checks and logs; find every setting |
| [Development](docs/development.md) | Use the tools and the tests, and see how releases work |
| [Frontend](docs/frontend.md) | Write the frontend's side of the login |
| [Production](docs/production.md) | Put the stack on a server |
| [Decision records](docs/adr/README.md) | See why each big choice was made |

## Stack

[FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy](https://docs.sqlalchemy.org/en/20/) 2 (async) · [Alembic](https://alembic.sqlalchemy.org/) · [Keycloak](https://www.keycloak.org/), reached with [httpx](https://www.python-httpx.org/) and [PyJWT](https://pyjwt.readthedocs.io/) · [structlog](https://www.structlog.org/) · [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) · [uv](https://docs.astral.sh/uv/) · [pytest](https://docs.pytest.org/)

---

Built by [Prgmturi](https://github.com/Prgmturi) · [Claude](https://claude.ai) was an excellent teammate 🤖
