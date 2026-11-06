# fastapi-starter

![Python](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![CI](https://github.com/Prgmturi/fastapi_starter/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/Prgmturi/fastapi_starter)

A starting point for a backend in FastAPI, built to teach as much as to be used. Login, database, logs, errors, tests and deployment are already in place. A new feature goes on top of them, and the structure shows where each piece of code belongs.

## What is included

- **Login** through Keycloak, a separate server that keeps the users and their passwords. The API never sees a password: it checks the signed token that comes with each request.
- **An architecture CI enforces.** Three parts, `core`, `adapters` and `features`, and one rule: imports go down. A build fails when a module breaks it.
- **An example to copy**, `features/notes`, with its business rules in plain Python, tested without a database.
- **PostgreSQL** with async SQLAlchemy, and migrations that CI checks against the models.
- **One format for the errors of the API** (RFC 9457) and for every log line (JSON outside development).
- **Tests at three levels:** unit tests, integration tests on a real Postgres, and a login through the whole stack.
- **Deployment:** a Docker image for every release, and a compose file for one server.

## Start in five minutes

It takes Docker.

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
| `keycloak` | http://localhost:8080 | The login server. Its console: user `admin`, password `admin` |
| `keycloak-db` | | Keycloak's Postgres |

Keycloak already has a user for the app: `testuser`, password `testuser-dev-password`. To see a whole login work, install [uv](https://docs.astral.sh/uv/) and run `uv run pytest -m e2e`: it logs `testuser` in, calls the API with the token, and writes and deletes a note.

## How it is built

[The architecture guide](docs/architecture.md) explains the design from the simple to the complex. Its first level is enough to add a feature in the right place.

### One request, from start to end

```
HTTP request: POST /notes
   │
   ▼
features/notes/api/router.py        reads the request (schemas/request.py), answers (schemas/response.py)
   │   before it runs, CurrentUser checks the token of the request:
   │   signed by Keycloak, and not expired (core/auth/, adapters/keycloak/)
   ▼
features/notes/domain/service.py    the rules: create the note for this user
   │   through a port, domain/protocols.py
   ▼
features/notes/persistence/         the SQL, in the transaction of the request
   │
   ▼
PostgreSQL
```

Every step, with the way back: [One request, all the way](docs/architecture.md#one-request-all-the-way).

### How a login works

Users log in on Keycloak, not on the API:

1. The frontend sends the user to Keycloak's login page, whose address comes from `GET /auth/login`.
2. After the password, Keycloak sends the user back to the frontend with a code. The frontend hands the code to the API, which trades it with Keycloak for two tokens (`POST /auth/token`).
3. The frontend sends the access token with every call. The API checks Keycloak's signature on it by itself, without calling Keycloak.
4. The access token lasts a few minutes. `POST /auth/refresh` gets a new one with the refresh token, which stays in a cookie that JavaScript cannot read.

Step by step, with the reasons and the code behind each step: [the authentication guide](docs/authentication.md).

### Three parts, one rule

| Folder | What lives there |
|---|---|
| `core/` | What every feature needs: the ports, the auth logic, the database, the settings, the logs, the errors |
| `adapters/` | The code that talks to a service outside the app, one folder for each: `keycloak/` |
| `features/` | What the API does: its endpoints |

The rule: **a module imports only from the parts below its own.** The entry points (`main.py`, `serve.py`, `healthcheck.py`) are at the top. Below them sits `bootstrap.py`, then `features/` and `adapters/`, then `core/`. Features and adapters never import each other: a feature asks for a port, and `bootstrap.py` hands it the adapter. CI checks the rule on every push.

What a port, an adapter or a domain is: [Words used here](docs/architecture.md#words-used-here). The reasons behind each choice: [the decision records](docs/adr/README.md).

## A first feature

A new feature starts as a copy of `features/notes`, with three layers: `api/` for the routes, `persistence/` for the table and the SQL, `domain/` for the rules in plain Python. A feature with no rules of its own can stay flat, as `features/auth` is.

The stack above needs no `.env`. Commands that run on the machine do: without it Alembic looks for Postgres on port 5432, and the stack is on 5433. So, once:

```bash
uv sync
cp .env.example .env
docker compose up --wait db
uv run alembic upgrade head                               # a new migration starts from the last one
docker compose exec db createdb -U appbase appbase_test   # for the integration tests
```

Then copy the example, rename it, register its router and write its migration. The exact commands, what goes where, and the rules a copy must keep: [Add a feature](docs/architecture.md#add-a-feature).

## Everyday tasks

### Protect a route

```python
from fastapi_starter.core.auth.dependencies import AdminUser, CurrentUser


@router.get("/profile")  # any user who is logged in
async def profile(user: CurrentUser) -> ProfileResponse:
    return ProfileResponse(username=user.username)


@router.get("/admin/profile")  # admin or superadmin
async def admin_profile(user: AdminUser) -> ProfileResponse:
    return ProfileResponse(username=user.username)
```

Without a token the route answers 401, and without the role 403. The roles, and how to give one to a user: [the authentication guide](docs/authentication.md#roles).

### Return an error

```python
from fastapi_starter.core.exceptions import NotFoundError

raise NotFoundError("Note", note_id)  # 404, with a body the client can read
```

Which exception fits: [When something fails](docs/architecture.md#when-something-fails). Every field of the answer: [the operations guide](docs/operations.md#errors).

### Read and write the database

The simple way, for a feature with no rules of its own:

```python
from fastapi_starter.core.database import BaseRepository, DbSession
from fastapi_starter.core.exceptions import NotFoundError


class ProductRepository(BaseRepository[Product]):
    model = Product


@router.get("/products/{product_id}")
async def get_product(product_id: int, db: DbSession) -> ProductResponse:
    product = await ProductRepository(db).get_by_id(product_id)
    if product is None:
        raise NotFoundError("Product", product_id)
    return ProductResponse.model_validate(product)
```

`Product` is a model on `Base`, and `ProductResponse` the schema of the answer, with `from_attributes=True`. `DbSession` opens one transaction for each request, and commits it before the response leaves. When each road fits: [The database is not an adapter](docs/architecture.md#the-database-is-not-an-adapter). Pages, background work, migrations: [the database guide](docs/database.md).

### Change the database

Change a model, then:

```bash
uv run alembic revision --autogenerate -m "what changes"
uv run alembic upgrade head
```

CI fails when a model changes without its migration.

### Add a setting or a service

The steps: [Add a setting](docs/architecture.md#add-a-setting) and [Add an external service](docs/architecture.md#add-an-external-service).

### Run the tests

```bash
uv run pytest                  # the unit tests: no database, no Keycloak
uv run pytest -m integration   # on a real Postgres, in the database appbase_test
uv run pytest -m e2e           # a login through the running stack
```

More in [the development guide](docs/development.md).

### Run the app on the machine

```bash
uv sync
uv run pre-commit install         # ruff, gitleaks and commitlint on every commit
cp .env.example .env
docker compose stop api           # if the whole stack is up: its container holds port 8000
docker compose up --wait db keycloak
uv run alembic upgrade head
uv run uvicorn fastapi_starter.main:create_app --factory --reload
```

## Configuration

Settings come from environment variables, or from `.env` in the root of the repository. `.env.example` lists them all, each with a comment. In staging and production the app refuses to start while a development value is left, and names it. Every setting: [the operations guide](docs/operations.md#settings).

## Production

`compose.prod.yaml`, over `compose.yaml`, runs the stack on one server: the image of a release, Keycloak behind a TLS proxy, every secret from the server's `.env`. [The production guide](docs/production.md) goes from the first start to the backups, with a checklist before going live.

## Learn more

| Guide | Read it to |
|---|---|
| [Architecture](docs/architecture.md) | Level 1: add a feature in the right place. Level 2: understand each choice, what checks it, and its limits |
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
