# fastapi-starter

![Python](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![CI](https://github.com/Prgmturi/fastapi_starter/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/Prgmturi/fastapi_starter)

A backend template built with FastAPI to learn and apply real architectural patterns — hexagonal architecture, SOLID, clean separation of concerns. Useful as a starting point for future projects: the infrastructure is already there, you just add features.

## What's in here

| Layer | What it does |
|---|---|
| **Auth** | Full OAuth2 + PKCE flow via Keycloak. JWT validation through JWKS with key rotation. Refresh tokens in HttpOnly cookies. |
| **Architecture** | Hexagonal (Ports & Adapters). Core logic talks only to protocols — swap Keycloak for Auth0 without touching `AuthService`. |
| **Database** | Async PostgreSQL with SQLAlchemy 2.0. Connection pooling, session lifecycle, base repository pattern. |
| **Config** | Pydantic Settings, layered by domain (`AppSettings`, `DatabaseSettings`, etc.), loaded from `.env`. |
| **Logging** | structlog. One format for every line, uvicorn's and SQLAlchemy's too: JSON in production with service metadata, colorized in development. Request IDs on every log line. |
| **Errors** | One format for every error: RFC 9457 problem details (`application/problem+json`). Domain exceptions (`NotFoundError`, `UnauthorizedError`, ...) with global handlers; no internal details reach the client. |
| **Testing** | Fully async. The unit tests need no database or auth server and ignore the local `.env`; the integration tests run on a real Postgres, in CI too. CI fails below a coverage threshold. |

## Architecture

The project is split into two layers that don't bleed into each other:

```
core/       ← infrastructure: auth, database, config, logging, errors
features/   ← business logic: your endpoints go here
```

`core/` defines behavior through `Protocol` classes (ports). Concrete implementations (adapters) live alongside them but are only wired together in one place — `setup.py`. This means `AuthService` has no idea what PyJWT is, `JWKSManager` has no idea what SQLAlchemy is, and adding a feature doesn't require touching infrastructure code.

CI checks these rules on every push and pull request, so breaking one fails the build:

- `uv run lint-imports` checks the import contracts in `pyproject.toml` (`[tool.importlinter]`). The layers are the entry points (`main`, `serve`, `healthcheck`) → `setup`, `exception_handlers` → `features` → `core`, and a module never imports from a layer above its own. Protocols import no adapter, `AuthService` imports neither PyJWT nor httpx, `core/auth/` never touches the database, and routers don't import httpx. A broken contract prints what to do instead.
- mypy checks that each adapter still matches its port: `setup.py` stores every adapter in `app.state` through a variable typed as the port.
- ruff rejects imports inside functions (`PLC0415`).

```
src/fastapi_starter/
├── main.py                  # App factory + lifespan
├── serve.py                 # The image's command: uvicorn with the SERVER_* settings
├── healthcheck.py           # The image's health probe
├── setup.py                 # Composition root — the only place that knows everything
├── exception_handlers.py    # Exceptions → RFC 9457 error responses
├── core/
│   ├── auth/                # JWT validation, JWKS, Keycloak claim extraction
│   ├── config/              # Settings by domain, loaded from .env
│   ├── database/            # Async engine, session factory, base repository
│   ├── logging/             # structlog config + request logging middleware
│   ├── body_limit.py        # Request body over SERVER_MAX_BODY_SIZE → 413
│   ├── error_middleware.py  # Unexpected exceptions → 500, inside the middleware stack
│   ├── exceptions.py        # Domain exception hierarchy
│   ├── problem_details.py   # RFC 9457 error body, also declared in OpenAPI
│   ├── protocols.py         # Cross-cutting contracts
│   └── security.py          # Security headers middleware
└── features/
    ├── auth/                # Login, token exchange, refresh, logout, /me
    └── health/              # /health/live and /health/ready
```

## Getting started

**Prerequisites:** Docker. To work on the code, also Python 3.13 and [uv](https://docs.astral.sh/uv/) 0.13 or later (an older uv stops with an error in this project: run `uv self update`).

```bash
git clone https://github.com/Prgmturi/fastapi_starter.git
cd fastapi_starter
docker compose up --build --wait
```

That starts the whole stack of `compose.yaml`, with development values and no `.env` to write:

| Service | On the host | What it is |
|---|---|---|
| `api` | http://localhost:8000, docs at `/docs` | the app, built from `docker/Dockerfile` |
| `migrate` | | `alembic upgrade head`, then it exits; the API starts only after it succeeds |
| `db` | `localhost:5433` | the app's Postgres |
| `keycloak` | http://localhost:8080, console user `admin`, password `admin` | Keycloak, in development mode |
| `keycloak-db` | | Keycloak's Postgres |

`uv run pytest -m e2e` logs the test user in through Keycloak and calls the API with the token, as a frontend would (CI does it on every push). The ports come from `SERVER_PORT`, `KEYCLOAK_PORT` and `DATABASE_PORT`, exported or in `.env`.

### Keycloak

On its first start Keycloak imports the realm of `docker/keycloak/realm-dev.json`:

- realm `fastapi-starter`, with the roles `superadmin`, `admin`, `collaborator` and `user`
- client `fastapi-backend`: confidential, standard flow only, redirect URIs `http://localhost:*`, secret `fastapi-backend-dev-secret`
- user `testuser`, password `testuser-dev-password`, role `user`

These values are public, so the realm is for development only: with `APP_ENVIRONMENT=production` the app refuses that secret. Changes made in the console stay in Keycloak's volume, and a realm that already exists is not imported again. To start again from the file, remove Keycloak's volume: `docker compose down`, then `docker volume rm <project>_keycloak_db_data`, where `<project>` is the folder name; the app's data is in another volume.

To have the API check `aud`: in the client's *Client scopes* tab open `fastapi-backend-dedicated` and add a mapper of type *Audience*, with *Included Client Audience* `fastapi-backend` and *Add to access token* on. Then set `KEYCLOAK_AUDIENCE=fastapi-backend`.

### Working on the code

Run the app on the host, with Postgres and Keycloak from the stack:

```bash
uv sync
uv run pre-commit install         # ruff and commitlint on every commit, as CI runs them
cp .env.example .env              # the stack's values, as the host sees them
docker compose up --wait db keycloak
uv run alembic upgrade head
uv run uvicorn fastapi_starter.main:create_app --factory --reload
```

Open http://localhost:8000/docs.

## Authentication flow

```
GET  /auth/login    → returns authorization URL (PKCE)
POST /auth/token    → exchanges code for tokens; refresh token set as HttpOnly cookie
POST /auth/refresh  → refreshes access token using the cookie
POST /auth/logout   → revokes refresh token, clears cookie
GET  /auth/me       → decodes bearer JWT via JWKS, returns User
```

JWT validation uses `JWKSManager`, which caches Keycloak's public keys (`KEYCLOAK_JWKS_CACHE_TTL`) and fetches them again when a token names an unknown key, as after a key rotation. It calls Keycloak one request at a time and at most once every `KEYCLOAK_JWKS_MIN_REFRESH_INTERVAL` seconds (default 30). If Keycloak is unreachable, the keys already in the cache keep working; a token whose key is not cached gets 503, so the client retries instead of logging the user out.

`/auth/token` and `/auth/refresh` answer with `Cache-Control: no-store`, so no browser or proxy keeps the access token. `/auth/refresh` and `/auth/logout` act on the cookie, which the browser sends by itself: a request whose `Origin` is not in `SERVER_CORS_ORIGINS` gets 403 before Keycloak is called. List your frontend there even when a proxy serves it on the same origin as the API. A request without `Origin`, such as one from curl or a mobile app, passes.

Set `KEYCLOAK_ALLOWED_REDIRECT_URIS` to the frontend's callback URLs (a JSON list). `/auth/login` and `/auth/token` then refuse any other `redirect_uri` with 422: the authorization code goes to that address, and a pattern in Keycloak's *Valid redirect URIs* such as `http://localhost:*` lets any port through. The comparison is exact, so `http://localhost:3000/callback/` is a different URI. Unset, only Keycloak checks.

The API accepts only access tokens (`typ: Bearer`) issued to `KEYCLOAK_CLIENT_ID` or to a client listed in `KEYCLOAK_ALLOWED_CLIENTS` (`azp`). ID tokens, refresh tokens and the tokens of other clients in the realm get 401, even though Keycloak signs them with the same keys. Up to 30 seconds of clock difference with Keycloak are tolerated.

## Adding a feature

```bash
mkdir -p src/fastapi_starter/features/products
touch src/fastapi_starter/features/products/{__init__,router,schemas}.py
```

In `router.py`:

```python
from fastapi import APIRouter
from fastapi_starter.core.auth.dependencies import CurrentUser, AdminUser
from fastapi_starter.core.database.dependencies import DbSession

router = APIRouter(prefix="/products", tags=["Products"])

@router.get("/")
async def list_products(user: CurrentUser, db: DbSession):
    ...
```

Register in `main.py` inside `create_app()`, alongside the existing routers:

```python
from fastapi_starter.features.products.router import router as products_router

# inside create_app():
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(products_router)  # add yours here
```

`CurrentUser`, `AdminUser`, `DbSession` are type aliases — FastAPI resolves the entire dependency chain automatically.

## Protecting endpoints

```python
from fastapi_starter.core.auth.dependencies import CurrentUser, AdminUser, CollabUser, require_roles
from fastapi_starter.core.auth.schemas import RoleEnum

# Any authenticated user
@router.get("/profile")
async def profile(user: CurrentUser): ...

# Admin or superadmin
@router.get("/stats")
async def stats(user: AdminUser): ...

# Collaborator, admin or superadmin
@router.get("/drafts")
async def drafts(user: CollabUser): ...

# Custom role check — import Annotated, User, Depends alongside the rest
@router.delete("/users/{id}")
async def delete_user(user: Annotated[User, Depends(require_roles([RoleEnum.SUPERADMIN]))]): ...
```

Roles form a hierarchy: superadmin > admin > collaborator. `SuperAdminUser`, `AdminUser` and `CollabUser` let through their role and every role above it; `user` is not part of the hierarchy. `require_roles` lets through only the roles you list, and a role that does not exist stops the app at startup. A user without the role gets 403 with `"detail": "Permission denied"`: the response does not say which roles were needed.

A role in the token that `RoleEnum` does not know is skipped. The first time a role shows up, the app logs it as the warning `unknown_role_skipped`, with its name, so a role written wrong in Keycloak shows up in the logs and not only as a 403. The roles Keycloak gives every user, `offline_access`, `uma_authorization` and `default-roles-<realm>`, are skipped without a line.

## Errors

Every error response is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem document, sent as `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Product with id '3' not found",
  "resource": "Product",
  "identifier": 3
}
```

- `status`, `title` and `detail` are always there. `title` is the standard phrase of the status code; `detail` explains what went wrong in this request.
- An invalid request (422) adds `errors`, one entry per invalid field: `{"loc": ["query", "limit"], "msg": "Input should be a valid integer, …", "type": "int_parsing"}`. The rejected value is not sent back.
- To return an error from your code, raise a subclass of `AppExceptionError` from `core/exceptions.py` (`NotFoundError`, `ConflictError`, `ForbiddenError`, …). Its `details` become extra members, like `resource` and `identifier` above.
- OpenAPI documents this format as the `default` response of every route.
- Every response has an `X-Request-ID` header, a 500 from a route included: the logs of that request carry the same id. The exception is a 500 caused by a bug in a middleware: Starlette answers it outside every middleware, so it has none of their headers, and only its log lines carry the id. An unexpected error answers only `"An unexpected error occurred."`; the cause and the traceback go to the logs, also with `APP_DEBUG=true`.

## Health checks

- `GET /health/live` answers 200 while the process runs. The Docker `HEALTHCHECK` calls it with `python -m fastapi_starter.healthcheck`, which sends the first `SERVER_TRUSTED_HOSTS` entry as `Host` and `SERVER_PORT` as port: the probe passes the trusted-host check that real requests pass, on the port the image's command (`python -m fastapi_starter.serve`) listens on.
- `GET /health/ready` answers 200 when the instance can serve requests and 503 when a check fails. The body is a status report, not a problem document, and gives only the status of each check: `{"status": "unhealthy", "checks": {"database": {"status": "unhealthy"}, "auth": {"status": "healthy"}}}`. The endpoint needs no token, so the cause goes to the logs only, as `readiness_check_failed`. A check that takes more than 2 seconds counts as failed.
- The auth check does not call Keycloak: it passes while the signing keys are cached. If Keycloak goes down, the instances keep validating tokens with those keys and stay ready.

## Logs

Every line the process writes has one format: JSON outside development, with the timestamp, the level and the service fields (`service`, `version`, `environment`), and colorized columns in development. The records of uvicorn, SQLAlchemy and httpx go through the same formatter, with the name of their logger in `logger`; a traceback stays inside its line, in `exception`. `APP_LOG_LEVEL` applies to them too.

- Every request has an id, in all its log lines (`request_id`) and in the `X-Request-ID` response header. A request that comes with an `X-Request-ID` of up to 64 letters, digits, `.`, `_` or `-` keeps it, so the proxy's log and the app's share the id; any other value is replaced with a new one. The proxy must set the header itself, over the client's, or the client picks the id: with Nginx, `proxy_set_header X-Request-ID $request_id;`, and `$request_id` in its `log_format`. CORS exposes the header, so a frontend on another origin can read it, for example to show it with an error.
- `request_started` names the client, with `client_ip` and `user_agent`. The query string is not logged: it can hold personal data or tokens. The request lines of the health probes (`/health/...`) are DEBUG, since Docker's `HEALTHCHECK` alone would write two lines every 30 seconds.
- Behind a proxy, uvicorn takes the client's address from `X-Forwarded-For` only on connections from an address in `SERVER_FORWARDED_ALLOW_IPS`, by default `["127.0.0.1"]`. In a container the proxy has another address: set it to that address, or to its network (`["172.18.0.0/16"]`), or `client_ip` is always the proxy's. Never `*` while the port can be reached without the proxy: anyone could choose the address the logs show, and production refuses it. The image's command passes the setting to uvicorn; the uvicorn command used in development reads uvicorn's own `FORWARDED_ALLOW_IPS` variable instead.
- uvicorn's access line is off: `request_completed` says the same, with the request id and the duration, and the access line also carries the query string. To have it back, delete the line that sets `uvicorn.access` to `WARNING` in `core/logging/config.py`.
- With `--workers` or `--reload`, uvicorn's parent process never calls the app factory, so its few lines (start and stop) keep uvicorn's format. The Docker image runs one process unless `SERVER_WORKERS` says otherwise: to scale, run more containers.

## Running tests

```bash
uv run pytest                              # all tests but the integration and end-to-end ones
uv run pytest tests/core/auth/            # a module
uv run pytest tests/core/auth/test_service.py::TestValidateToken  # one class
uv run pytest --cov                        # with coverage, as CI runs it
uv run pytest -m integration               # only the integration tests, on a real Postgres
uv run pytest -m e2e                       # a login through the running stack (docker compose up)
```

Tests are fully async. Outside `tests/integration/` they use `AsyncMock` stubs — no real database or Keycloak instance needed. The root `conftest.py` provides fixtures for the app, HTTP client, mock services, and sample users at different role levels.

Tests never read your local `.env` or exported `APP_*`, `KEYCLOAK_*` variables: an autouse fixture in `conftest.py` switches both off. A test that needs specific settings builds them and passes them to `create_app(settings)`. CI runs the suite twice, the second time with a production-like `.env`, and fails if coverage drops below `fail_under` in `pyproject.toml`.

### Integration tests

The tests in `tests/integration/` run on a real Postgres, for what a mock cannot show, such as a commit that the database refuses. `uv run pytest` leaves them out, even when you name their file; add `-m integration`, which runs only them. They read `TEST_DATABASE_*` (exported or in `.env`, see `.env.example`) and no other setting, and they refuse a database whose name does not end in `_test`, because they create and drop tables in it. Create that database once, in the `db` service of the stack:

```bash
docker compose exec db createdb -U appbase appbase_test   # -U: DATABASE_USER
```

CI runs them in a job of their own, with its own Postgres. They do not count towards the coverage threshold.

## Database access

`DbSession` gives a route one session and one transaction: it commits when the route returns, before the response is sent, and rolls back when anything fails, so a failed commit answers 500, never 201. Repositories extend `BaseRepository`, which has `get_by_id`, `get_page`, `create` and `delete`:

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

`get_page` sorts by primary key, so a row updated between two pages is neither skipped nor shown twice. It refuses a `limit` above `MAX_PAGE_SIZE` (100): bound the query parameter as above and the client gets 422 instead of 500. A row deleted from an earlier page still shifts the next pages by one; that is the limit of offset paging.

Background tasks and streaming responses run after `DbSession` has closed its session. Give them the database provider and open a session there:

```python
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

## Database migrations

```bash
uv run alembic revision --autogenerate -m "add products table"
uv run alembic upgrade head
uv run alembic downgrade -1
```

Migrations read `DATABASE_*` and no other setting, so they run before the new version starts, without the rest of the configuration: in `compose.yaml` the `migrate` service runs `alembic upgrade head` from the app's image, and the API starts only after it succeeds. CI runs every migration up to head, compares the result with the models (`alembic check`: a model changed without its migration fails the build), then down to the base and up again.

Define models by subclassing `Base` from `core/database/base.py`. Import them in `alembic/env.py` before running autogenerate — if you forget, `--autogenerate` aborts with an explanation instead of emitting a migration that drops every table in the database.

Indexes and constraints get their names from the naming convention in `core/database/base.py`: `pk_<table>`, `uq_<table>_<columns>`, `ix_<table>_<columns>`, `fk_<table>_<columns>_<referred table>`. Postgres would otherwise pick its own names, and the downgrades Alembic writes could not drop them. A `CheckConstraint` needs a `name=`, which becomes `ck_<table>_<name>`; without it the model fails at import. Change the convention only before the first migration: afterwards it renames existing constraints.

## Configuration reference

All application settings are read from `.env` in the repo root — see
`.env.example` for the full list. `compose.yaml` reads from the same file
only the ports and the database credentials; the `api` service gets the
rest of its settings in `compose.yaml` itself.

Two Postgres instances in `compose.yaml`: `db`, the app's, on
`DATABASE_PORT` (5433), and `keycloak-db`, reachable only inside the stack.

Key environment variables:

```bash
APP_ENVIRONMENT=development        # development | staging | production
APP_LOG_LEVEL=INFO                 # DEBUG | INFO | WARNING | ERROR | CRITICAL, any case
DATABASE_PORT=5433
DATABASE_COMMAND_TIMEOUT=30        # seconds per query; a slower one answers 500
KEYCLOAK_CLIENT_SECRET=...         # required
KEYCLOAK_PUBLIC_URL=                # production: the address the browser sees, = KC_HOSTNAME
SERVER_CORS_ORIGINS=["http://localhost:3000"]
SERVER_MAX_BODY_SIZE=65536         # bytes; a larger request body gets 413
SERVER_PORT=8000                   # the image listens and probes here
SERVER_TIMEOUT_GRACEFUL_SHUTDOWN=5 # seconds open requests get at shutdown, below docker stop's 10
SERVER_FORWARDED_ALLOW_IPS=["127.0.0.1"]  # the proxy, behind one: see Logs
```

The image starts with `python -m fastapi_starter.serve`, which runs uvicorn with the `SERVER_*` settings: host, port, workers, keep-alive, the shutdown time and the trusted proxies. Another command replaces it whole, as for the migrations: `docker run <image> alembic upgrade head`.

`/docs`, `/redoc`, and `/openapi.json` are only available when `APP_ENVIRONMENT=development`.

With `APP_ENVIRONMENT=production` the app refuses to start while a development or example value is left: `APP_DEBUG=true`, Keycloak's public address on http, an empty or example `KEYCLOAK_CLIENT_SECRET`, `KEYCLOAK_COOKIE_SECURE=false`, no `KEYCLOAK_ALLOWED_REDIRECT_URIS`, the default or example `DATABASE_PASSWORD`, `DATABASE_ECHO=true` (it logs every query with its values), `*` in `SERVER_CORS_ORIGINS`, `SERVER_TRUSTED_HOSTS` or `SERVER_FORWARDED_ALLOW_IPS`, or only localhost in `SERVER_TRUSTED_HOSTS`. The error lists every variable to change at once, without their values. The checks are in `core/config/production.py`.

In every environment the pool settings have bounds, because SQLAlchemy reads some values in a surprising way: `DATABASE_POOL_SIZE` at least 1 (0 means no limit), `DATABASE_POOL_MAX_OVERFLOW` at least 0 (-1 means no limit), `DATABASE_POOL_TIMEOUT`, `DATABASE_POOL_RECYCLE` and the two database timeouts above 0 (`DATABASE_POOL_RECYCLE=0` opens a new connection for every query). A value out of range stops the startup with an error that names the variable.

## Releases

Commits follow [Conventional Commits](https://www.conventionalcommits.org/): commitlint checks every commit of a pull request and its title, which becomes the commit on `master` when the pull request is squashed. [release-please](https://github.com/googleapis/release-please) keeps a release pull request open with the next version and the CHANGELOG. Merging it:

- tags `vX.Y.Z` and publishes the GitHub release;
- publishes the image `ghcr.io/prgmturi/fastapi_starter:X.Y.Z`, and `:latest`;
- has already bumped the version in `pyproject.toml`, `uv.lock` and the `image:` lines of `compose.prod.yaml`.

Under 1.0, `feat` and `fix` raise the patch number and a breaking change (`!`) the minor one.

## Production

`compose.prod.yaml`, over `compose.yaml`, runs the stack on one server: the image of a release, Keycloak in production mode behind a TLS proxy, every password and secret from the server's `.env`, the API and Keycloak on `127.0.0.1` only, and logs that rotate:

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

[`docs/production.md`](docs/production.md) is the guide, from the first start of Keycloak to backups, and [`docs/nginx.conf`](docs/nginx.conf) the proxy: TLS, the request id, rate limits, and only the public paths of Keycloak.

## Stack

- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://docs.sqlalchemy.org/en/20/) 2.0 (async)
- [Alembic](https://alembic.sqlalchemy.org/)
- [Keycloak](https://www.keycloak.org/), reached with [httpx](https://www.python-httpx.org/) and [PyJWT](https://pyjwt.readthedocs.io/)
- [structlog](https://www.structlog.org/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [uv](https://docs.astral.sh/uv/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)

---

Built by [Prgmturi](https://github.com/Prgmturi) · [Claude](https://claude.ai) was an excellent teammate 🤖
