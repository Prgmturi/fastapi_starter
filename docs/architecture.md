# Architecture

How the code is split, the one rule that holds it together, and what CI checks. The reasons behind each choice are in [the decision records](adr/README.md).

## Three parts

| Folder | What lives there | Example |
|---|---|---|
| `core/` | What every feature needs: the ports, the auth logic, the database, the settings, the logs, the errors | `core/auth/protocols.py` |
| `adapters/` | The code that talks to a service outside the app, one folder for each | `adapters/keycloak/` |
| `features/` | What the API does: the endpoints | `features/notes/` |

Around them sit `bootstrap.py`, which builds the adapters and hands them to the app, and the three entry points, `main.py`, `serve.py` and `healthcheck.py`.

A **port** is a `Protocol` class: it says what a service must be able to do, and holds no code that does it. `OAuthProvider` is a port: log in, exchange a code, refresh, log out. An **adapter** is a class that does it with a real library or service: `KeycloakClient` implements `OAuthProvider` with httpx and Keycloak.

The code that uses a port never sees the adapter behind it. `AuthService` checks tokens through two ports, `TokenDecoder` and `ClaimExtractor`, so it does not know PyJWT. The auth router asks for an `OAuthProvider`, so it does not know Keycloak's URLs.

## The rule: imports go down

```
main.py · serve.py · healthcheck.py      the entry points
            │
        bootstrap.py                     builds the adapters, wires them to their ports
            │
  features/        adapters/             never import each other
            │
          core/
```

A module imports only from the parts below its own. Features and adapters sit side by side, and neither imports the other: a feature asks for a port, and `bootstrap.py` hands it the adapter.

Inside a feature with rules of its own, the same rule repeats on three layers: `api/` → `persistence/` → `domain/` (The example feature, below).

## What CI checks

On every push and pull request, so that breaking a rule fails the build:

- **Import contracts**, in `pyproject.toml` (`[tool.importlinter]`), checked by `uv run lint-imports`:
  - the layers above: entry points → `bootstrap`, `exception_handlers` → `features` and `adapters` → `core`;
  - ports import no adapter;
  - `AuthService` imports neither PyJWT nor httpx;
  - `core/auth/` and the Keycloak adapters never touch the database;
  - routers do not import httpx;
  - the health probe loads neither the app nor FastAPI, SQLAlchemy or httpx;
  - the business layer of a feature imports no framework and no database;
  - inside a feature, `api` → `persistence` → `domain`.

  A broken contract prints what to do instead.
- **mypy** checks that each adapter still matches its port: `bootstrap.py` stores every adapter in `app.state` through a variable typed as the port.
- **ruff** refuses imports inside functions (`PLC0415`).
- **Tests that import modules in a new process.** import-linter reads the import statements of each module, but not what the `__init__.py` of a package pulls in. These tests check what is really loaded: `core` loads no feature and no adapter, the health probe loads none of what its contract forbids, a domain loads no framework.
- **`tests/test_import_contracts.py`** checks that every module a contract names exists. import-linter stays silent when a forbidden module does not, so a contract that names a module after it moved would check nothing.

## The files

```
src/fastapi_starter/
├── main.py                  # The app factory, create_app(), and the lifespan
├── serve.py                 # The image's command: uvicorn with the SERVER_* settings
├── healthcheck.py           # The image's health probe
├── bootstrap.py             # Builds the adapters and wires them: the only place that knows everything
├── exception_handlers.py    # Exceptions → RFC 9457 error responses
├── adapters/
│   └── keycloak/            # Login and tokens, signing keys, token checks, claims → User
├── core/
│   ├── auth/                # Ports, AuthService, route dependencies, the refresh cookie
│   ├── config/              # Settings by domain, read from the environment and .env
│   ├── database/            # Async engine, sessions, base repository, helpers for Alembic
│   ├── logging/             # structlog setup and the request logging middleware
│   ├── body_limit.py        # A request body over SERVER_MAX_BODY_SIZE → 413
│   ├── error_middleware.py  # Unexpected exceptions → 500, inside the middleware stack
│   ├── exceptions.py        # The domain exceptions (NotFoundError, ...)
│   ├── problem_details.py   # The RFC 9457 error body, also declared in OpenAPI
│   ├── protocols.py         # Ports shared by several parts
│   └── security.py          # Security headers
└── features/
    ├── auth/                # Login, token exchange, refresh, logout, /me
    ├── health/              # /health/live and /health/ready
    └── notes/               # The example to copy: api/, domain/, persistence/
```

## Entry points

`main.py`, `serve.py` and `healthcheck.py` are started from outside the code, and no module imports them: the layers contract forbids it. A search for their callers finds only the tests.

| Module | Started by | When |
|---|---|---|
| `main.py` | uvicorn, which calls `create_app()` (`--factory`) | When the server process starts: through `serve.py` in the image, `uv run uvicorn ... --reload` in development |
| `serve.py` | Docker, as the image's `CMD` | When the container starts: `docker compose up`, production |
| `healthcheck.py` | Docker, as the image's `HEALTHCHECK` | Every 30 seconds while the container runs |

The `migrate` service starts the same image with another command, `alembic upgrade head`.

## The example feature

`features/notes/` keeps the notes of each user, at `/notes`. It is the feature to copy, and it has three layers:

| Layer | What it holds | What it may import |
|---|---|---|
| `api/` | the routes (`router.py`), the service of each request (`dependencies.py`), what the client sends (`schemas/request/`) and what the API returns (`schemas/response/`) | the two layers below, FastAPI, `core` |
| `persistence/` | the table (`models.py`) and the repository that implements the port of the domain (`repository.py`) | `domain/`, SQLAlchemy, `core` |
| `domain/` | the business rules in plain Python: the entity (`note.py`), the port (`protocols.py`), the service (`service.py`) | the standard library and `core.exceptions` |

Because the domain imports no framework and no database, its rules are tested with a repository kept in memory (`tests/features/notes/fakes.py`), in milliseconds.

What the example does on purpose, and a copy should keep:

- The owner comes from the token (`user.id`), never from the body. The request schemas refuse unknown fields (`extra="forbid"`), so a client that sends `owner_id` gets 422.
- Every query of the repository filters by owner in the SQL itself. A note of another user answers 404, like a missing one, so no one learns which ids exist.
- The domain decides the id, a UUID, and the times. Nothing has to be read back from the database after a save.
- A length limit is a business rule: `TITLE_MAX_LENGTH` lives in `domain/note.py`, and the request schema and the column take it from there.

A feature with no rules of its own can stay flat, as `features/auth/` and `features/health/` are: a `router.py` that takes `DbSession`, and a repository on `BaseRepository` (see [the database guide](database.md)). Choose the three layers when the feature has rules worth testing without a database.

The README shows how to copy the example into a feature of your own.

### Dropping the example

`git grep -il notes` lists every file that names it. Besides its two folders and `tests/integration/test_notes.py`, they are:

- `main.py`, which includes its router;
- two contracts in `pyproject.toml`: "Inside a feature", and the one of the domains, if no other feature has a domain;
- the migration in `alembic/versions/`;
- the smoke test in `.github/workflows/ci.yml` and `tests/test_smoke.py`;
- the calls to `/notes` in `tests/e2e/test_login.py`;
- a few lines of `tests/test_main.py`, `tests/test_package.py`, `tests/test_alembic.py`, `tests/test_import_contracts.py` and `tests/core/database/test_migrations.py`.

A database that already has the table needs a migration that drops it.

## Another identity provider

It means another folder next to `adapters/keycloak/`, its settings in `core/config/`, and its wiring in `bootstrap.py`. Two places still name Keycloak outside the adapters: the auth router reads the allowed redirect URIs from `KeycloakSettings`, and the production checks in `core/config/production.py` name the `KEYCLOAK_*` variables.

The database is not an adapter: features work with SQLAlchemy sessions directly, so SQLAlchemy is part of `core/` ([decision record 0005](adr/0005-database.md)).
