# Architecture

How the code is organised and why, from the first folder to the last check. The text assumes FastAPI and nothing about hexagonal architecture. Each chapter starts from a problem the previous ones leave open, so the file reads from the top down.

- **[Level 1: Use the template](#level-1-use-the-template)** is enough to add a feature in the right place: [Where the code goes](#where-the-code-goes), [Imports go down](#imports-go-down), [A service outside the app](#a-service-outside-the-app), [Rules without a database](#rules-without-a-database), [Add a feature](#add-a-feature).
- **[Level 2: Understand every choice](#level-2-understand-every-choice)** gives the reason behind each choice, with its [decision record](adr/README.md): [Who builds the adapters](#who-builds-the-adapters), [How the app starts and stops](#how-the-app-starts-and-stops), [One request, all the way](#one-request-all-the-way), [When something fails](#when-something-fails), [The database is not an adapter](#the-database-is-not-an-adapter), [Why the API checks tokens itself](#why-the-api-checks-tokens-itself), [What checks each rule](#what-checks-each-rule), [Add a setting](#add-a-setting), [Add an external service](#add-an-external-service).
- **At the end:** [Limits and trade-offs](#limits-and-trade-offs), [The files](#the-files), [Words used here](#words-used-here).

Paths start at `src/fastapi_starter/`, unless they begin with `tests/` or name a file in the root of the repository.

## Level 1: Use the template

### Where the code goes

In a small FastAPI project everything fits in the routes: the request, the rule, the SQL, the call to another service. That stops working when a second feature needs the same login, or when a rule has to change without touching the SQL. By then nothing says where new code belongs, and every change touches all of it.

Here each kind of code has one place, in three folders:

| Folder | What lives there | Example |
|---|---|---|
| `features/` | What the API does for its clients: routes, business rules, tables | `features/notes/`, the notes of each user |
| `adapters/` | The code that talks to a service outside the app, one folder for each service | `adapters/keycloak/` |
| `core/` | What every feature needs: the login checks, the database session, the settings, the logs, the errors | `core/exceptions.py` |

A **feature** is one folder of `features/`, on one subject. **`core`** is the part all the others share, and it knows none of them. Around the three folders sit `bootstrap.py`, which builds the adapters, and the modules that start the app: `main.py`, `serve.py` and `healthcheck.py`.

A request crosses them like this:

```
POST /notes
   │
   ▼
features/notes/api/router.py                reads the request, writes the response
   │   core/auth/ checks the token first
   ▼
features/notes/domain/service.py            the rule: create the note for this user
   │
   ▼
features/notes/persistence/repository.py    the SQL
   │
   ▼
PostgreSQL
```

**Why:** new code has one obvious place, and a change stays inside one folder.

**Cost:** more folders than a single `app.py`, so a small feature looks heavy at first. The full reasoning is in [decision record 0001](adr/0001-hexagonal-architecture.md).

**In short**

- `features/` holds what the API does, `adapters/` talks to the outside, and `core/` holds what they share.
- A feature is one folder on one subject, such as `features/notes/`.
- `bootstrap.py` and the modules that start the app sit around the three folders.

### Imports go down

Three folders alone do not keep code apart, because Python lets any module import any other. If `core/exceptions.py` imported from `features/notes/`, every feature would load notes, and a bug there would break them all. If a feature imported `adapters/keycloak/`, replacing Keycloak would mean editing the feature.

So the parts have an order, and **a module imports only from the parts below its own**:

```
main.py · serve.py · healthcheck.py      start the app; nothing imports them
            │
bootstrap.py · exception_handlers.py     connect the parts
            │
    features/        adapters/           side by side: neither imports the other
            │
          core/                          imports none of the above
```

Each height of this schema is a **layer**. The rule is not advice: `pyproject.toml` declares it, and `uv run lint-imports` compares it with the import statements of every module, on every push:

```toml
# pyproject.toml
layers = [
    # ...
    "fastapi_starter.main | fastapi_starter.serve | fastapi_starter.healthcheck",
    "fastapi_starter.bootstrap | fastapi_starter.exception_handlers",
    # ...
    "fastapi_starter.features | fastapi_starter.adapters",
    "fastapi_starter.core",
]
```

A rule on imports that a tool checks is an **import contract**. `|` puts two parts at the same height, and forbids imports between them. So `from fastapi_starter.adapters.keycloak.client import KeycloakClient` in a router fails the build, and [What checks each rule](#what-checks-each-rule) shows what it prints.

**Why:** a change can break only the layers above it, never the ones below.

**Cost:** a feature cannot simply import an adapter it needs, so it takes one more step, which the next chapter shows. The full reasoning is in [decision record 0001](adr/0001-hexagonal-architecture.md).

**In short**

- A module imports only from the layers below its own.
- Features and adapters sit side by side, and never import each other.
- `uv run lint-imports` checks the rule on every push.

### A service outside the app

The login needs Keycloak, the service that keeps the users and their passwords: the API sends it a code and gets tokens back. The obvious place for that call is the route:

```python
@router.post("/token")
async def exchange_token(
    request: TokenRequest,
    settings: Annotated[KeycloakSettings, Depends(get_keycloak_settings)],
) -> AccessTokenResponse:
    async with httpx.AsyncClient() as client:
        answer = await client.post(
            settings.token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.client_id,
                "client_secret": settings.client_secret.get_secret_value(),
                "code": request.code,
                "code_verifier": request.code_verifier,
                "redirect_uri": request.redirect_uri,
            },
        )
    tokens = answer.json()
    return AccessTokenResponse(
        access_token=tokens["access_token"],
        token_type=tokens["token_type"],
        expires_in=tokens["expires_in"],
    )
```

This route works, but it is tied to Keycloak in two ways:

- Replacing Keycloak means rewriting the four routes of `features/auth/router.py` that depend on it, because its addresses and its fields sit inside them.
- A test of the route needs a running Keycloak, or a copy of its HTTP answers, even just to check that a wrong code answers 401.

`uv run lint-imports` refuses this code too, because a contract forbids httpx in a router. Moving the call to a class in `adapters/` does not help on its own: the route would have to import that class, and [a feature never imports an adapter](#imports-go-down).

The way out starts from what the route really needs, which is a result and not the way to get it. That need is written down in `core/`, which features and adapters may both import:

```python
# core/auth/protocols.py
class OAuthProvider(Protocol):
    def build_authorization_url(
        self,
        redirect_uri: str,
        code_challenge: str,
        state: str | None = None,
        scope: str = "openid profile email",
    ) -> str: ...

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> TokenResponse: ...

    async def refresh_token(self, refresh_token: str) -> TokenResponse: ...

    async def logout(self, refresh_token: str) -> None: ...
```

A Python `Protocol` lists methods and holds no code: any class with those methods matches it, without inheriting from it. The signatures use the app's own types, such as `TokenResponse`, and none from httpx.

The code that does the work lives in `adapters/keycloak/client.py`. `KeycloakClient` has the same methods, and the call to Keycloak of the first example moved inside it, with httpx and the same fields. It neither inherits from `OAuthProvider` nor imports it.

The route now asks for an `OAuthProvider` and calls it, with no httpx and no address of Keycloak:

```python
# features/auth/router.py
async def exchange_token(
    request: TokenRequest,
    # ...
    oauth_provider: Annotated[OAuthProvider, Depends(get_oauth_provider)],
    # ...
) -> AccessTokenResponse:
    # ...
    tokens = await oauth_provider.exchange_code(
        code=request.code,
        code_verifier=request.code_verifier,
        redirect_uri=request.redirect_uri,
    )
    # ...
```

Only `bootstrap.py` knows both sides, because it sits above them. At startup it builds the client and stores it under the name that `get_oauth_provider` reads ([Who builds the adapters](#who-builds-the-adapters) covers this in full):

```python
# bootstrap.py
OAUTH_PROVIDER.set(app_state, KeycloakClient(settings, http_client))
```

With no inheritance, this line also keeps the two in step. `OAUTH_PROVIDER` is a `StateKey[OAuthProvider]`, so mypy compares the client with the protocol here, and a missing method fails the build.

Since the route knows only `OAuthProvider`, a test can give it any object with the same methods. The fixture `mock_oauth_provider` builds a **fake**, a stand-in with no real service behind it, and the fixture `app_with_oauth` hands it to the route:

```python
# tests/features/auth/conftest.py
mock.exchange_code = AsyncMock(return_value=sample_token_response)
# ...
app.dependency_overrides[get_oauth_provider] = lambda: mock_oauth_provider
```

A code that Keycloak refuses then takes one statement to simulate, and the whole of `tests/features/auth/test_router.py` runs in under a second, with no network:

```python
# tests/features/auth/test_router.py
mock_oauth_provider.exchange_code.side_effect = UnauthorizedError("Invalid code")
```

The pieces fit together like this. At startup `bootstrap.py` provides the object on the left, and in a test `dependency_overrides` provides the one on the right:

```
features/auth/router.py
  exchange_token asks for an OAuthProvider
        │
        ▼
core/auth/protocols.py
  OAuthProvider: the methods, no code
        ▲                                 ▲
        │ same methods                    │ same methods
        │                                 │
adapters/keycloak/client.py        tests/features/auth/conftest.py
  KeycloakClient                     mock_oauth_provider
        │ httpx
        ▼
     Keycloak
```

`OAuthProvider` is a **port**: a `Protocol` that says what a service must be able to do, with no code that does it. `KeycloakClient` is an **adapter**: a class that does it with a real library or service. A project built around ports and adapters follows the **hexagonal architecture**.

**Why:** a route stays the same when the service behind it changes, and it can be tested without that service.

**Cost:** more files than a flat project, and one more step from a route to the code that runs. The full reasoning is in [decision record 0001](adr/0001-hexagonal-architecture.md).

Replacing Keycloak then means another folder next to `adapters/keycloak/`, its settings, and its wiring in `bootstrap.py`, while the calls in the routes stay the same ([Add an external service](#add-an-external-service)). A few things outside the adapters still name Keycloak, such as `KeycloakSettings` in this same router ([Limits and trade-offs](#limits-and-trade-offs)).

**In short**

- A port (`OAuthProvider`, in `core/`) says what a service must be able to do, and an adapter (`KeycloakClient`, in `adapters/`) does it with a real library.
- A route asks for the port, `bootstrap.py` hands it the adapter, and mypy checks that the two match.
- The service can change behind the port, and a test can replace it with a fake.

### Rules without a database

Each user reaches only their own notes, and a note of another user looks like one that does not exist, so no one learns which ids are taken. The obvious place for that rule is the route:

```python
@notes_router.get("/{note_id}")
async def get_note(
    note_id: UUID, user: CurrentUser, session: DbSession
) -> NoteResponse:
    statement = select(NoteRow).where(
        NoteRow.id == note_id, NoteRow.owner_id == user.id
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Note", str(note_id))
    return NoteResponse.model_validate(row)
```

This route works, but the rule has no place of its own: half of it is a `where`, the other half an `if`, and every route on notes has to repeat both. A test of the rule needs a real Postgres, or a copy of what SQLAlchemy would answer.

`features/notes/` gives the rule a place, by splitting the feature in three layers:

| Layer | What it holds | What it knows |
|---|---|---|
| `api/` | The routes (`router.py`), the wiring of each request (`dependencies.py`), what the client sends (`schemas/request.py`) and gets back (`schemas/response.py`) | FastAPI and pydantic |
| `persistence/` | The table (`models.py`) and the queries (`repository.py`) | SQLAlchemy |
| `domain/` | The note (`note.py`), the port (`protocols.py`), the rules (`service.py`) | Plain Python: no framework and no database |

The rule now reads on its own:

```python
# features/notes/domain/service.py
class NoteService:
    # ...
    def __init__(self, repository: NoteRepository) -> None:
        self._repository = repository

    # ...
    async def get_note(self, owner_id: str, note_id: UUID) -> Note:
        # ...
        note = await self._repository.get(owner_id, note_id)
        if note is None:
            raise NotFoundError("Note", str(note_id))
        return note
```

`NoteRepository`, in `domain/protocols.py`, is a port like `OAuthProvider`, with five methods: `page`, `get`, `add`, `save` and `delete`. `SqlNoteRepository`, in `persistence/repository.py`, implements it with SQLAlchemy: every query filters by owner, and each row becomes a `Note`, a plain dataclass. `InMemoryNoteRepository`, in `tests/features/notes/fakes.py`, implements it with a dict, so a test runs the real rule with a fake behind it:

```python
# tests/features/notes/test_domain.py
async def test_another_users_note_is_not_found(self, service):
    # ...
    note = await service.create_note(OTHER, "not mine", "")

    with pytest.raises(NotFoundError) as exc_info:
        await service.get_note(OWNER, note.id)
```

All 17 tests of that file run in under a tenth of a second. The route keeps only HTTP (`return NoteResponse.model_validate(await service.get_note(user.id, note_id))`), and `api/dependencies.py` joins the two layers below it:

```python
# features/notes/api/dependencies.py
def get_note_service(session: DbSession) -> NoteService:
    # ...
    repository: NoteRepository = SqlNoteRepository(session)
    return NoteService(repository)
```

The annotation on the variable makes mypy compare the repository with its port, as `StateKey` does in `bootstrap.py`.

```
features/notes/api/router.py                FastAPI: reads the request, writes the response
        │
        ▼
features/notes/domain/service.py            NoteService: the rule
        │ calls the port NoteRepository, domain/protocols.py
        ├──────────────────────────────────────┐
        ▼ in the app                           ▼ in a test
features/notes/persistence/repository.py    tests/features/notes/fakes.py
  SqlNoteRepository                           InMemoryNoteRepository
```

Calls and imports do not run the same way. The call goes from the rule to the SQL, but the import goes from the SQL to the rule: `persistence/` imports `domain/`, and `domain/` imports neither of the others. So the layers, from the top, are `api/`, `persistence/`, `domain/`, and two contracts check them: "Inside a feature", and "The business layer of a feature knows no framework and no database".

The **domain** is the rules of a feature, in plain Python. A **repository** is the object that reads and writes its rows. `SqlNoteRepository` does the work of an adapter, yet it lives in the feature, and [The database is not an adapter](#the-database-is-not-an-adapter) says why.

**Why:** a rule can be read, changed and tested with no framework and no database.

**Cost:** rows are mapped to `Note` and back, which a route with its own SQL would not need. The full reasoning is in [decision record 0005](adr/0005-database.md).

**In short**

- The domain holds the rules in plain Python, and reaches its data through a port.
- `persistence/` implements that port with SQLAlchemy, and a test implements it with a dict.
- `api/` holds HTTP, and joins the two layers below it for each request.

### Add a feature

Copying `features/notes/` is the quickest way to a new feature. A careless copy, though, can lose a rule that no check sees: an owner read from the body passes mypy and every contract, and lets one user write as another. So a copy starts from what goes where, and ends on what it must keep.

| To add | It goes in | Example |
|---|---|---|
| A route | `features/<name>/api/router.py` | `create_note` |
| What the client sends or gets back | `features/<name>/api/schemas/` | `CreateNoteRequest`, `NoteResponse` |
| A business rule | `features/<name>/domain/` | `NoteService`, `TITLE_MAX_LENGTH` |
| A table and its queries | `features/<name>/persistence/` | `NoteRow`, `SqlNoteRepository` |
| A call to a service outside the app | `adapters/<service>/`, behind a port | [Add an external service](#add-an-external-service) |
| A setting | `core/config/` | [Add a setting](#add-a-setting) |
| Something every feature needs | `core/` | `core/exceptions.py` |

The three layers fit a feature with rules worth testing without a database. A feature with no rules of its own stays **flat**: a `router.py`, as in `features/auth/` and `features/health/`, plus a repository on `BaseRepository` if it needs a table ([The database is not an adapter](#the-database-is-not-an-adapter)).

#### Prepare the machine, once

The stack of the README needs no `.env`. The commands below run on the machine, though, and those need one: without it Alembic looks for Postgres on port 5432 with the user `postgres`, while the stack publishes it on 5433 with the user `appbase`. Alembic writes a new migration only from a database at the last one, and otherwise stops with `Target database is not up to date`. The integration tests also need a database of their own, whose name ends in `_test`:

```bash
uv sync
cp .env.example .env
docker compose up --wait db
uv run alembic upgrade head
docker compose exec db createdb -U appbase appbase_test
```

#### Copy the example

For a feature called `tasks`:

1. **Copy the code and its tests:**

   ```bash
   cp -r src/fastapi_starter/features/notes src/fastapi_starter/features/tasks
   cp -r tests/features/notes tests/features/tasks
   cp tests/integration/test_notes.py tests/integration/test_tasks.py
   ```

   Then replace `notes` and `note` inside the copies, capitals too (`CreateNoteRequest` becomes `CreateTaskRequest`), and rename `domain/note.py` to `domain/task.py`. A plain find and replace is enough.
2. **Register the router** in `create_app()` of `main.py`: import `tasks_router` from `fastapi_starter.features.tasks.api.router`, and add `app.include_router(tasks_router)` after the others.
3. **Write the migration.** Alembic finds the new table by itself, because the module is called `models`:

   ```bash
   uv run alembic revision --autogenerate -m "create tasks table"
   uv run alembic upgrade head
   ```

   Read the file it writes in `alembic/versions/` before committing it.
4. **Tidy and check.** The new names change the order of some imports, and Alembic writes in its own style:

   ```bash
   uv run ruff check --fix
   uv run ruff format
   uv run pytest
   uv run pytest -m integration
   uv run mypy src/
   uv run lint-imports
   ```

The contracts and the test of the names read `features.*` and every route, so they apply to the copy with no change.

#### What a copy must keep

- **The owner comes from the token** (`user.id`), never from the body. The request schemas refuse unknown fields (`extra="forbid"`), so a client that sends `owner_id` gets 422.
- **Every query filters by owner**, in the SQL itself. A note of another user answers 404, like a missing one.
- **The domain decides the id and the times**, so nothing has to be read back from the database after a save.
- **A length limit is a business rule.** `TITLE_MAX_LENGTH` lives in `domain/note.py`, and the request schema and the column take it from there.
- **The names say the direction.** What the client sends ends in `Request`, what it gets back in `Response`. `test_openapi_names_say_the_direction`, in `tests/test_main.py`, checks every route.

Only the last one has a check of its own. The others rest on the tests that come with the copy, so those tests stay.

#### Drop the example

`git grep -il notes` lists every file that names it. Besides its two folders and `tests/integration/test_notes.py`, they are:

- `main.py`, which includes its router;
- two contracts in `pyproject.toml`, if no other feature has the three layers: "Inside a feature", and the one of the domains (`tests/test_import_contracts.py` says which);
- the migration in `alembic/versions/`;
- the smoke test in `.github/workflows/ci.yml` and `tests/test_smoke.py`;
- the calls to `/notes` in `tests/e2e/test_login.py`;
- a few lines of `tests/test_main.py`, `tests/test_package.py`, `tests/test_alembic.py`, `tests/test_import_contracts.py` and `tests/core/database/test_migrations.py`.

A database that already has the table needs a migration that drops it.

**Why:** a copy starts with working tests, and every check applies to it at once.

**Cost:** the renaming is by hand, and most of the rules above rest on tests that a careless copy can delete. When each of the two shapes fits: [decision record 0005](adr/0005-database.md).

**In short**

- A new feature starts as a copy of `features/notes/`, or as a flat `router.py` if it has no rules of its own.
- The commands run on the machine, so they need a `.env`, a database at the last migration, and the database `appbase_test`.
- The owner from the token and the filter on every query are the rules a copy must keep.

## Level 2: Understand every choice

### Who builds the adapters

A route asks for an `OAuthProvider`, and `Depends(get_oauth_provider)` hands it one. Something has to build that object once, with its settings and its HTTP client. A feature cannot, since it cannot import the adapter. Building it when a module is imported would read the settings at import, and a test could not pass its own.

There is a second problem. `app.state`, the natural place to keep the object, takes any attribute and has no types. A class with a method missing would be stored without a word, and fail only on the request that calls that method.

`bootstrap.py` solves the first problem: it sits above features and adapters, so it may import both, and it is the only module that does. The second is solved by a small class, which gives each name in `app.state` one type:

```python
# core/state.py
class StateKey[T]:
    # ...
    def __init__(self, name: str) -> None:
        self.name = name

    def set(self, state: State, value: T) -> None:
        setattr(state, self.name, value)

    def get(self, state: State) -> T:
        # ...
        value: T = getattr(state, self.name)
        return value
```

The key is declared with the port as its type, next to the code that reads it:

```python
# features/auth/router.py
OAUTH_PROVIDER = StateKey[OAuthProvider]("oauth_provider")


def get_oauth_provider(request: Request) -> OAuthProvider:
    # ...
    return OAUTH_PROVIDER.get(request.app.state)
```

`bootstrap.py` calls `.set()` at startup, where mypy compares the object with the port, and each request calls `.get()` and receives the port:

```
bootstrap.py              OAUTH_PROVIDER.set(app_state, KeycloakClient(...))    at startup
        │  stored in app.state; mypy has compared KeycloakClient with OAuthProvider
        ▼
features/auth/router.py   get_oauth_provider(request)                           at each request
        │  returned as an OAuthProvider
        ▼
features/auth/router.py   exchange_token(oauth_provider=...)
```

| Port | Key, next to the code that reads it | What `bootstrap.py` stores |
|---|---|---|
| `OAuthProvider` | `OAUTH_PROVIDER`, in `features/auth/router.py` | `KeycloakClient` |
| `TokenValidator` | `AUTH_SERVICE`, in `core/auth/dependencies.py` | `AuthService`, built on `JWKSTokenDecoder` and `KeycloakClaimExtractor` |
| `DatabaseProvider` | `DB_MANAGER`, in `core/database/dependencies.py` | `DatabaseManager` |

A write by hand, such as `app_state.oauth_provider = KeycloakClient(...)`, would pass mypy, because `app.state` has no types. So `tests/core/test_state.py` refuses any write outside a key. Its one exception is `app.state.settings`, which `main.py` stores before anything starts.

The one place that builds the objects and connects them is the **composition root**. A piece of code that receives what it needs, instead of building it, uses **dependency injection**: FastAPI's `Depends` is one way to do it, and `app.dependency_overrides` is how a test swaps the object.

**Why:** another provider changes one module and leaves the routes alone, and mypy checks every adapter against its port.

**Cost:** a key and a getter for each port, and one more step to follow from a route to the code that runs. The full reasoning is in [decision record 0001](adr/0001-hexagonal-architecture.md).

**In short**

- Only `bootstrap.py` builds adapters, because only it may import both features and adapters.
- A `StateKey` gives a name in `app.state` the type of its port, so mypy checks each adapter where it is stored.
- A route receives the port through `Depends`, and a test swaps it with `dependency_overrides`.

### How the app starts and stops

`main.py` used to build the app when it was imported, from the settings of the environment. One invalid variable then broke every tool that imported the package, pytest included, and a test could not build an app with settings of its own. A second risk sits at startup: when a service fails halfway, or a Ctrl+C arrives in the middle, the services already open must still close.

So building the app and opening its services are two separate steps. `create_app()` only builds: it reads the settings, sets up the logs, and registers the middleware, the error handlers and the routers, with no connection opened. The services open later, in `lifespan()`, when the server starts the app:

```
Docker: CMD                          development: uv run uvicorn ... --factory --reload
  │                                                   │
  ▼                                                   │
serve.py   uvicorn with the SERVER_* settings         │
  └───────────────────────┬───────────────────────────┘
                          ▼
main.py        create_app()        builds the app, opens nothing
                          │
                          ▼
main.py        lifespan()
bootstrap.py   start_services()    1. Postgres: the pool, and a SELECT 1
                                   2. the HTTP client for Keycloak
                                   3. AuthService: downloads the signing keys
                                   4. KeycloakClient
                          │
                          ▼
                  serves requests
                          │  docker stop: SERVER_TIMEOUT_GRACEFUL_SHUTDOWN seconds for open requests
                          ▼
bootstrap.py   shutdown_services() closes in reverse order: the HTTP client, then Postgres
```

Each service goes into a list as soon as it is open, so the `finally` closes what was opened, whatever ends the lifespan:

```python
# main.py
services: list[tuple[str, CleanupFn]] = []
try:
    await start_services(app.state, settings, services)
    # ...
    yield
    # ...
finally:
    await shutdown_services(services)
```

When Postgres or Keycloak is down at startup, the log has one line, `database_connection_failed` or `auth_service_init_failed`, then uvicorn prints the traceback once and the process exits with code 3. In `compose.yaml` the `api` service starts only after `db`, `migrate` and `keycloak`.

A function that builds and returns the app is an **app factory**. **`lifespan`** is the FastAPI hook that runs code before the first request and after the last one. An **entry point** is a module started from outside the code, and no module imports one, since the layers contract forbids it:

| Module | Started by | When |
|---|---|---|
| `main.py` | uvicorn, which calls `create_app()` (`--factory`) | When the server process starts: through `serve.py` in the image, `uv run uvicorn ... --reload` in development |
| `serve.py` | Docker, as the image's `CMD` | When the container starts |
| `healthcheck.py` | Docker, as the image's `HEALTHCHECK` | Every 30 seconds while the container runs |

The `migrate` service starts the same image with another command, `alembic upgrade head`.

**Why:** importing a module reads no setting and starts nothing, and a test builds as many apps as it needs.

**Cost:** `uvicorn fastapi_starter.main:app` does not work, because `app` does not exist: uvicorn needs `--factory`. The full reasoning is in [decision record 0004](adr/0004-app-factory.md).

**In short**

- `create_app()` builds the app and opens nothing, so importing it is safe.
- `lifespan()` opens the services through `bootstrap.py`, and closes whatever was opened, however it ends.
- `main.py`, `serve.py` and `healthcheck.py` are started from outside, and nothing imports them.

### One request, all the way

Why does a 400 have no security headers? Why does a failed write answer 500 and not 201? Why does a request with no token and an invalid body answer 401 and not 422? All three have the same answer: the order in which things run.

A **middleware** wraps every request: it sees the request on the way in, and the response on the way out. `register_middleware()`, in `bootstrap.py`, adds six, and the last one added runs first. This is `POST /notes`, from start to end:

```
POST /notes
   │  on the way in
   ▼
core/logging/middleware.py     LoggingMiddleware             the request id; logs request_started
Starlette                      TrustedHostMiddleware         Host not allowed: 400
core/security.py               SecureHeadersMiddleware       nothing yet
FastAPI                        CORSMiddleware                answers the preflights
core/body_limit.py             BodySizeLimitMiddleware       body over the limit: 413
core/error_middleware.py       UnhandledExceptionMiddleware  nothing yet
   │
   ▼
features/notes/api/router.py   create_note: its dependencies first, then its body
   │   core/auth/dependencies.py                CurrentUser: no valid token, 401
   │   features/notes/api/dependencies.py       NoteServiceDep: DbSession opens a session
   │   features/notes/api/schemas/request.py    CreateNoteRequest: invalid body, 422
   ▼
features/notes/domain/service.py                NoteService.create_note: a new Note
   ▼
features/notes/persistence/repository.py        SqlNoteRepository.add: the INSERT, not yet final
   ▼
core/database/dependencies.py                   the route has returned: COMMIT
   │  on the way out, in reverse order
   ▼
UnhandledExceptionMiddleware   an exception becomes a 500
CORSMiddleware                 adds the CORS headers
SecureHeadersMiddleware        adds the security headers
LoggingMiddleware              logs request_completed; adds X-Request-ID
   ▼
201, with a NoteResponse
```

A **preflight** is the `OPTIONS` request a browser sends first, to ask whether a page of another origin may call the API. At the default log level a request writes two lines, `request_started` and `request_completed`, both with the same `request_id`. By the second line the commit has already happened.

The commit runs before the response leaves because of one argument:

```python
# core/database/dependencies.py
async with db_manager.session_factory() as session:
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
# ...
DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
```

`scope="function"` ends the dependency when the route returns. With FastAPI's default, `"request"`, the commit would run after the response has left, and the client would get 201 for data that was never saved.

Each failure stops at its own place, and the place decides what the answer carries:

| What goes wrong | Where it stops | Answer | Logged between the two lines |
|---|---|---|---|
| `Host` not in `SERVER_TRUSTED_HOSTS` | `TrustedHostMiddleware` | 400 in plain text, with no security or CORS headers | Nothing |
| Body over `SERVER_MAX_BODY_SIZE` | `BodySizeLimitMiddleware` | 413, before the token is read | Nothing |
| No token, or an invalid one | `CurrentUser` | 401, even with an invalid body | `app_exception` |
| Invalid body, with a valid token | FastAPI, after the dependencies | 422, and the session rolls back | Nothing |
| The note does not exist | `NoteService`, then the handler of `AppExceptionError` | 404, and the session rolls back | `app_exception` |
| A bug in the route, or a failed commit | `UnhandledExceptionMiddleware` | 500, with every header | `unhandled_exception`, with the traceback |

The exceptions of the app stop before the six middleware see them: Starlette's own `ExceptionMiddleware`, closer to the routes, runs the handlers of `exception_handlers.py`. The response then goes out as any other does.

**Why:** a client never gets 201 for data that was not saved, and every failure has one place to look at.

**Cost:** the session is closed by the time a background task or a streaming response runs, so those open their own ([the database guide](database.md#work-after-the-response)). The full reasoning is in [decision record 0005](adr/0005-database.md).

**In short**

- Six middleware wrap every request, and the first one in is the last one out.
- A route resolves its dependencies before its body, so a missing token answers 401 even when the body is invalid.
- `DbSession` commits when the route returns and before the response leaves, so a failed commit answers 500.

### When something fails

A request can fail in many ways. Without a rule, FastAPI answers `{"detail": ...}`, a custom error answers something else, and a frontend needs three ways to read an error. It also cannot tell "log in again" from "try later". And when a library error, such as one from httpx, reaches a router, every route has to know that library.

The solution has two parts. First, the code raises the app's own exceptions, from `core/exceptions.py`, and an adapter turns every library error into one of them:

```python
# adapters/keycloak/client.py
except UNREACHABLE as e:
    # ...
    raise ServiceUnavailableError(
        "auth", retry_after=RETRY_AFTER_SECONDS
    ) from e
except httpx.HTTPError as e:
    # ...
    raise ExternalServiceError("Keycloak") from e
```

`OAuthProvider` promises those exceptions in its docstring: `UnauthorizedError`, `ServiceUnavailableError` and `ExternalServiceError`, and no other. So a route catches them, and never sees httpx:

```python
# features/auth/router.py
try:
    await oauth_provider.logout(current_refresh_token)
except (ExternalServiceError, ServiceUnavailableError, UnauthorizedError) as exc:
```

Second, one handler turns each exception into one format:

```
features/notes/domain/service.py   raise NotFoundError("Note", str(note_id))
adapters/keycloak/client.py        raise ServiceUnavailableError("auth", retry_after=...)
        │  an AppExceptionError, from core/exceptions.py
        ▼
exception_handlers.py              app_exception_handler: logs app_exception
        │
        ▼
core/problem_details.py            problem_response(): the body, as application/problem+json
```

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Note with id 'a3464280-862c-4fcc-b5a2-4c2ab011c108' not found",
  "resource": "Note",
  "identifier": "a3464280-862c-4fcc-b5a2-4c2ab011c108"
}
```

That body is a **problem document**, the format of RFC 9457. Each exception tells the client what to do next:

| Exception | Status | What happened | What the client does |
|---|---|---|---|
| `UnauthorizedError` | 401 | No token, or one that is not valid | Refresh once, then log in again |
| `ForbiddenError` | 403 | The token is valid, the role is missing | Say so: a refresh does not help |
| `NotFoundError` | 404 | Missing, or of another user | Say so |
| `ConflictError` | 409 | The request clashes with what exists | Say so |
| `ValidationError` | 422 | A value the rules refuse | Fix the value |
| `ExternalServiceError` | 502 | A service answered in a way the API does not expect, or refused the API's own client | Show an error: a fault of the server |
| `ServiceUnavailableError` | 503, with `Retry-After` | A service cannot be reached | Keep the user logged in, and try again later |
| Any other exception | 500 | A bug. The body says only `An unexpected error occurred.` | Show an error, with `X-Request-ID` |

With a 503 the service could not be reached, so the same request can succeed once it is back. With a 502 it answered, in a way the API cannot use. Postgres follows the same rule: a connection that cannot open is a 503 (`connect_or_unavailable`, in `core/database/manager.py`), and a query slower than `DATABASE_COMMAND_TIMEOUT` stays a 500, because there the query is the problem. Every message, field and log line: [the operations guide](operations.md#errors).

**Why:** a client reads every error with the same code, and can tell a retry from a login.

**Cost:** an adapter must translate every library error, and one it forgets becomes a 500. The full reasoning is in [decision record 0006](adr/0006-errors.md).

**In short**

- Code raises the exceptions of `core/exceptions.py`, and an adapter translates the errors of its library into them.
- `exception_handlers.py` turns each one into a problem document, RFC 9457.
- 503 means the same request can succeed later, 502 that the fault is on the server.

### The database is not an adapter

[A service outside the app](#a-service-outside-the-app) suggests a next step: a port for the database too, and an adapter in `adapters/postgres/`. Every query of every feature would then cross a port with a single implementation, and so would every transaction. All that would pay for replacing Postgres, which is not a goal of this template.

So SQLAlchemy is part of `core/`, which every feature may import:

| Piece | File | What it does |
|---|---|---|
| `DatabaseManager` | `core/database/manager.py` | The engine, the pool and the timeouts |
| `DbSession` | `core/database/dependencies.py` | One session and one transaction for each request |
| `BaseRepository` | `core/database/repository.py` | `get_by_id`, `get_page`, `create` and `delete` |
| `Base` | `core/database/base.py` | The base of every model, and the names of constraints |
| `DatabaseProvider` | `core/database/protocols.py` | The port the routes get: `health_check` and `session_factory`. `disconnect()` stays out, so only the lifespan can call it |

What matters is keeping the rules of a feature free of SQL, when it has rules. So a feature takes one of two roads:

| | Flat | Three layers |
|---|---|---|
| When | No rules of its own | Rules worth testing without a database |
| Where the SQL is | A repository on `BaseRepository`, next to the router | `persistence/`, behind a port of the domain |
| What the route handles | The SQLAlchemy model | A plain object, such as `Note` |
| What a test needs | A stub of the session, or a real Postgres | A fake that keeps data in memory |
| Example | [Read and write the database](../README.md#read-and-write-the-database), in the README | `features/notes/` |

`SqlNoteRepository` implements a port with a real library, which is what an adapter does. It stays in the feature for a reason the layers impose: its methods take and return `Note`, a type of the feature, and [an adapter cannot import a feature](#imports-go-down). So it has the role of an adapter, and the folder of the feature.

Two more rules keep the database in its place. `core/auth/` and `adapters/keycloak/` never touch it, and a contract ("Auth knows no database") checks that. Migrations read only `DATABASE_*`, so they run before a new version starts, without the rest of its settings. The details: [the database guide](database.md).

**Why:** a simple feature writes its queries directly, and a feature with rules still gets a domain free of SQL.

**Cost:** two roads to learn, and SQLAlchemy cannot be swapped without touching the features. The full reasoning is in [decision record 0005](adr/0005-database.md).

**In short**

- SQLAlchemy lives in `core/`, because replacing Postgres is not a goal and a port for every query would cost more than it gives.
- A feature with no rules uses `DbSession` and `BaseRepository` directly, and a feature with rules hides them behind a port.
- `SqlNoteRepository` acts as an adapter, but stays in the feature because it uses the feature's types.

### Why the API checks tokens itself

Every request has to say who is calling. The simplest way to know is to ask Keycloak each time. Then every request costs a call over the network, and a Keycloak that is down stops the whole API, even for users who are already logged in.

Keycloak signs its tokens instead. An access token is a **JWT**: a small JSON object and its signature, encoded as text. The API checks the signature with the **JWKS**, the public keys of the **realm**, the space in Keycloak that holds the users of the app. It downloads them at startup and keeps them in a cache. Only Keycloak holds the private key, so no one else can write a token that passes, and a normal request never calls Keycloak.

The check crosses two ports, because it depends on two things that change for different reasons: the JWT library, and the **claims**, the fields of the token, whose shape differs from one provider to another.

```
CurrentUser                      core/auth/dependencies.py    takes the Bearer token
└─ AuthService.validate_token    core/auth/service.py         knows only its ports
   ├─ port TokenDecoder          JWKSTokenDecoder, adapters/keycloak/jwks.py
   │  │                          PyJWT: the signature, the expiry, the issuer, typ and azp
   │  └─ KeyProvider             JWKSManager, adapters/keycloak/jwks_manager.py
   │                             the public keys, in a cache
   └─ port ClaimExtractor        KeycloakClaimExtractor, adapters/keycloak/extractors.py
                                 the claims of Keycloak become a User, with its roles
```

A contract ("AuthService knows no JWT or HTTP library") keeps PyJWT and httpx out of `AuthService`, so `core/auth/` stays the same with another provider. `KeyProvider` is a port too, but only `JWKSTokenDecoder` uses it and its keys are PyJWT's, so it stays in `adapters/keycloak/jwks.py`.

What each failure of Keycloak costs:

| Keycloak is down | What happens |
|---|---|
| A request with a token whose key is in the cache | It works: users stay logged in |
| A request with a token whose key is not in the cache | 503: the frontend retries instead of logging the user out |
| A login or a refresh | 503, until Keycloak is back |
| The API starts | It does not start: it needs the keys first |

The login itself still goes through Keycloak, and the refresh token lives in a cookie that JavaScript cannot read ([decision record 0003](adr/0003-refresh-token-in-a-cookie.md)). Every step of it, and each check on a token: [the authentication guide](authentication.md).

**Why:** a normal request costs no network call, and users stay logged in while Keycloak is down.

**Cost:** an access token stays valid until it expires, a few minutes, even after a logout, and the API cannot start without Keycloak. The full reasoning is in [decision record 0002](adr/0002-keycloak.md).

**In short**

- The API checks the signature of each token with Keycloak's public keys, without calling Keycloak.
- `AuthService` knows two ports: `TokenDecoder` for the JWT library, `ClaimExtractor` for the claims of the provider.
- While Keycloak is down, tokens keep working, and logins and refreshes answer 503.

### What checks each rule

A rule written only in a guide does not last: the first hurried commit breaks it, and no one notices. So every rule of the chapters above has a tool behind it, which runs on every push and pull request. The output below is real, from breaking each rule on purpose:

| Rule | Checked by | When broken, it prints |
|---|---|---|
| Imports go down | `uv run lint-imports` | `fastapi_starter.features is not allowed to import fastapi_starter.adapters` |
| Inside a feature, `api` → `persistence` → `domain` | `uv run lint-imports` | `fastapi_starter.features.notes.persistence is not allowed to import fastapi_starter.features.notes.api` |
| A domain knows no framework and no database | `uv run lint-imports`, `tests/test_package.py` | `fastapi_starter.features.notes.domain is not allowed to import sqlalchemy` |
| A router does not import httpx | `uv run lint-imports` | `fastapi_starter.features.notes.api.router is not allowed to import httpx` |
| Ports import no adapter | `uv run lint-imports` | `fastapi_starter.core.protocols is not allowed to import fastapi_starter.adapters` |
| `AuthService` knows no JWT or HTTP library | `uv run lint-imports` | `fastapi_starter.core.auth.service is not allowed to import jwt` |
| Auth knows no database | `uv run lint-imports` | `fastapi_starter.core.auth is not allowed to import sqlalchemy` |
| The health probe loads only what it needs | `uv run lint-imports`, `tests/test_healthcheck.py` | `fastapi_starter.healthcheck is not allowed to import fastapi` |
| An adapter matches its port | `uv run mypy src/` | `"KeycloakClient" is missing following "OAuthProvider" protocol member` |
| `app.state` is written through a key | `tests/core/test_state.py` | `Store these through a StateKey (core/state.py): ['bootstrap.py: oauth_provider']` |
| The names say the direction | `tests/test_main.py` | `AssertionError: assert {'NoteOut'} == set()` |
| No import inside a function | `uv run ruff check` | ``PLC0415 `import` should be at the top-level of a file`` |
| `core` loads no feature and no adapter | `tests/test_package.py` | `assert "['fastapi_starter.adapters']" == '[]'` |
| A contract names modules that exist | `tests/test_import_contracts.py` | `"Ports import no adapter" names fastapi_starter.core.database.gone, which matches no module` |
| Every model is in a module called `models` | `tests/core/database/test_migrations.py` | `Alembic never sees [...]: move each to a module called models under features/` |
| A model does not change without its migration | `alembic check`, in the CI job "Integration tests" | `FAILED: New upgrade operations detected: [('add_column', None, 'notes', ...)]` |
| No development value outside development | `Settings`, at startup | `refusing to start in staging:`, then one line for each value |

A broken contract also says what to do. A router that imports the Keycloak adapter breaks two contracts, and for the first one it prints:

```text
Layers: main, serve, healthcheck -> bootstrap, exception_handlers -> features,
adapters -> core
--------------------------------------------------------------------------------
---------------

fastapi_starter.features is not allowed to import fastapi_starter.adapters:

- fastapi_starter.features.notes.api.router ->
fastapi_starter.adapters.keycloak.client (l.1)


A module imports from a layer above its own, or a feature and an adapter
import each other. core is what features and adapters build on,
bootstrap.py wires the adapters to their ports, main.py builds the app.
Move the shared code down a layer, or have the layer above pass it in,
as bootstrap.py does with the adapters.
```

And `KeycloakClient` with `logout` renamed prints, at the line that stores it:

```text
src/fastapi_starter/bootstrap.py:154: error: Argument 2 to "set" of "StateKey" has incompatible type "KeycloakClient"; expected "OAuthProvider"  [arg-type]
src/fastapi_starter/bootstrap.py:154: note: "KeycloakClient" is missing following "OAuthProvider" protocol member:
src/fastapi_starter/bootstrap.py:154: note:     logout
```

Two kinds of test cover what the tools leave out. import-linter reads the import statements of each module, but not what the `__init__.py` of a package pulls in, so `tests/test_package.py` and `tests/test_healthcheck.py` import the modules in a new process and look at what was really loaded. And import-linter stays silent when a forbidden module does not exist, so a contract that names a module after it moved would check nothing: `tests/test_import_contracts.py` catches that.

Which CI job runs what: [the development guide](development.md#what-ci-runs). What none of the checks sees: [Limits and trade-offs](#limits-and-trade-offs).

**Why:** a broken rule stops the build at once, and the error says what to do.

**Cost:** CI takes longer, and when a module moves its contracts move with it. The full reasoning is in [decision record 0001](adr/0001-hexagonal-architecture.md).

**In short**

- Each rule has a tool behind it, and breaking the rule fails the build on that push.
- `uv run lint-imports` checks who imports whom, mypy checks that adapters match ports, and tests check the rest.
- Tests that load modules in a new process cover what import-linter cannot see.

### Add a setting

A value read with `os.environ` in the middle of a route has no type and no default, and a typo shows up only when that route runs. Worse, a development value can reach production and no one notices, since nothing fails.

So a setting is a typed field, checked when the app starts. `SERVER_MAX_BODY_SIZE` shows the shape:

```python
# core/config/server.py
max_body_size: int = Field(
    default=64 * 1024,
    gt=0,
    description="Largest request body in bytes; a larger one gets 413",
)
```

The steps, and what each one prevents:

1. **Add the field** to the class of its subject in `core/config/`. The class gives the prefix: `ServerSettings` reads `SERVER_*`. Give it the bounds that make sense (`gt=0`), and use `SecretStr` for a secret, so that logs and errors show stars. A value out of range stops the startup, with an error that names the variable and hides the value.
2. **Describe it in `.env.example`**, with a comment. `tests/core/config/test_settings.py` builds the settings from that file, so an example that is no longer valid fails the tests.
3. **Read it from the settings the app received**: `create_app()` passes `settings.server` to `register_middleware()`, and a dependency reads `request.app.state.settings`. Only `create_app()` calls `get_settings()`, so the settings of a test reach everything.
4. **Pass it to the container, if it changes by environment.** The `api` service gets only what the compose files name, so the variable goes in `compose.yaml` or `compose.prod.yaml`, and in [the production guide](production.md#the-servers-env).
5. **Refuse its development value, if that value is dangerous elsewhere**, in `production_problems()`:

   ```python
   # core/config/production.py
   if database.echo:
       problems.append(
           "DATABASE_ECHO is true: every query goes to the logs with its values"
       )
   ```

   Staging and production then refuse to start, and the error lists every value to change at once, without showing them. Add a test next to the others in `tests/core/config/test_settings.py`.

A new subject takes a new class in `core/config/`, with its own `env_prefix`, a copy of the `model_config` of the others (`hide_input_in_errors=True` keeps the values of `.env` out of errors), and a field in `Settings`. `tests/conftest.py` takes its list of classes from those fields, so the tests ignore the new variables of the machine with no change.

**Why:** a wrong value stops the startup with an error that names it, instead of failing on some request later.

**Cost:** a setting can touch up to four files: its class, `.env.example`, a compose file and `production_problems()`. The full reasoning is in [decision record 0007](adr/0007-development-values.md).

**In short**

- A setting is a typed field of a class in `core/config/`, read once and checked at startup.
- The code reads it from the settings `create_app()` received, so a test can pass its own.
- A development value that is dangerous elsewhere goes in `production_problems()`, and staging and production refuse it.

### Add an external service

[A service outside the app](#a-service-outside-the-app) shows the idea on Keycloak. Adding another service brings a question that chapter leaves open: where does the port go? Next to the feature that needs it seems natural, but the adapter has to use the types in the signatures of the port, and [an adapter cannot import a feature](#imports-go-down). So the port and its types go in `core/`, which both may import.

Here is a mail service, as an example. The port, where `OutgoingMail`, in `core/mail/schemas.py`, is a pydantic model with the fields of a mail:

```python
# core/mail/protocols.py (new)
from typing import Protocol

from fastapi_starter.core.mail.schemas import OutgoingMail


class MailSender(Protocol):
    """Raises only ServiceUnavailableError and ExternalServiceError."""

    async def send(self, mail: OutgoingMail) -> None: ...
```

The adapter, which turns every error of its library into an exception of the app:

```python
# adapters/mail/client.py (new)
import httpx

from fastapi_starter.core.config.mail import MailSettings
from fastapi_starter.core.exceptions import (
    ExternalServiceError,
    ServiceUnavailableError,
)
from fastapi_starter.core.mail.schemas import OutgoingMail


class MailClient:
    def __init__(self, settings: MailSettings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = http_client

    async def send(self, mail: OutgoingMail) -> None:
        try:
            response = await self._client.post(
                self._settings.send_url, json=mail.model_dump()
            )
            response.raise_for_status()
        except (httpx.NetworkError, httpx.TimeoutException) as e:
            raise ServiceUnavailableError("mail", retry_after=5) from e
        except httpx.HTTPError as e:
            raise ExternalServiceError("Mail service") from e
```

The wiring, which goes in `start_services()`, with the HTTP client in `services` so that it closes at shutdown:

```python
# bootstrap.py (new lines)
mail_http = httpx.AsyncClient(timeout=settings.mail.request_timeout)
services.append(("mail_http_client", mail_http.aclose))
MAIL_SENDER.set(app_state, MailClient(settings.mail, mail_http))
```

A route then asks for it as `exchange_token` asks for its provider: `Annotated[MailSender, Depends(get_mail_sender)]`.

| Step | Where | If it goes wrong |
|---|---|---|
| 1. The port and its types | `core/mail/protocols.py`, `core/mail/schemas.py` | An adapter that imports a feature: `uv run lint-imports` |
| 2. The settings | `core/config/mail.py`, a field in `Settings`, `.env.example` | [Add a setting](#add-a-setting) |
| 3. The adapter | `adapters/mail/client.py` | A library error it does not translate: nothing stops it, and the route answers 500. A test with `httpx.MockTransport` shows it, as in `tests/adapters/keycloak/test_client.py` |
| 4. The key and its getter | `core/mail/dependencies.py`: `MAIL_SENDER`, `get_mail_sender()` | A write by hand to `app.state`: `tests/core/test_state.py` |
| 5. The wiring | `start_services()`, in `bootstrap.py` | A method that does not match the port: mypy. No wiring at all: nothing stops it, and the first request answers 500 |
| 6. The route | `features/<name>/`, which asks for the port | The adapter or httpx imported in a router: `uv run lint-imports` |
| 7. The tests | A fake through `app.dependency_overrides` for the route, `httpx.MockTransport` for the adapter | The coverage threshold, `fail_under` in `pyproject.toml` |
| 8. Production | `production_problems()`, `compose.prod.yaml`, and a check in `features/health/router.py` if the API cannot serve without the service | Nothing stops it: [the checklist](production.md#before-going-live) |

#### Another identity provider

It means another folder next to `adapters/keycloak/`, with new `OAuthProvider`, `TokenDecoder` and `ClaimExtractor` implementations, its settings in `core/config/`, and its wiring in `bootstrap.py`. `main.py` and `core/auth/` stay the same. What still names Keycloak outside the adapters is listed in [Limits and trade-offs](#limits-and-trade-offs).

**Why:** a new service touches the routes that use it and nothing else, and the adapter can be replaced later in the same way.

**Cost:** eight places for one service, against one `httpx.post` in a route. The full reasoning is in [decision record 0001](adr/0001-hexagonal-architecture.md).

**In short**

- The port and its types go in `core/`, because an adapter cannot import a feature.
- `bootstrap.py` builds the adapter inside `start_services()`, and closes what it opened.
- Most steps have a check behind them. The errors of the library, the wiring and production rest on tests and on the checklist.

## Limits and trade-offs

What the design does not do, or does not check. Each point below was checked on the code, some by breaking the rule on purpose.

**What the checks do not see**

- **Another HTTP client in a router.** The contract named "Routers reach external services only through ports" forbids only httpx: `import urllib.request` in a router passes.
- **What a domain may import.** Its contract is a list of bans, not of what is allowed: `import structlog` in `domain/` passes.
- **A feature that imports another feature.** No contract forbids it, at any layer. Today none does.
- **The fakes.** mypy runs on `src/` only, so it does not compare a fake with its port. `mock_oauth_provider` is an `AsyncMock` with no spec, which accepts any method.
- **The rules of a copy.** The owner from the token and the filter on every query rest on the tests of each feature.
- **A forgotten wiring.** A port with no adapter stored in `app.state` shows up only on the first request that needs it, as a 500.

**Keycloak outside the adapters**

- `features/auth/router.py` reads the allowed redirect URIs from `KeycloakSettings`.
- `core/config/keycloak.py` holds `KeycloakSettings`, because `Settings` gathers every section there and `core` never imports an adapter.
- `core/config/production.py` names the `KEYCLOAK_*` variables.

**Tokens**

- An access token stays valid until it expires, a few minutes, even after a logout: the API does not ask Keycloak.
- The API does not start while Keycloak is down, because it needs the signing keys first.

**The database**

- SQLAlchemy cannot be swapped without touching the features, on purpose ([The database is not an adapter](#the-database-is-not-an-adapter)).
- `SqlNoteRepository` has the role of an adapter, and the folder of the feature.
- A flat feature has no fake: its queries are tested with a stub of the session, or on a real Postgres.
- Paging is by offset: a row deleted from an earlier page shifts the next pages by one.
- A background task or a streaming response runs after the session has closed, and opens its own.

**Errors**

- Two answers are plain text, not problem documents, because they come from middleware the app does not write: `Invalid host header` (400, a `Host` not allowed) and `Disallowed CORS origin` (400, a preflight from an origin not allowed).
- A bug in a middleware answers 500 outside every middleware, so that response has no CORS or security headers and no `X-Request-ID`. Only its log lines carry the id.

**Deployment**

- `compose.prod.yaml` runs the stack on one server. More servers, or an orchestrator, are outside this template.

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
│   ├── config/              # Settings by subject, read from the environment and .env
│   ├── database/            # Async engine, sessions, base repository, helpers for Alembic
│   ├── logging/             # structlog setup and the request logging middleware
│   ├── body_limit.py        # A request body over SERVER_MAX_BODY_SIZE → 413
│   ├── error_middleware.py  # Unexpected exceptions → 500, inside the middleware stack
│   ├── exceptions.py        # The app's exceptions (NotFoundError, ...)
│   ├── problem_details.py   # The RFC 9457 error body, also declared in OpenAPI
│   ├── protocols.py         # Ports shared by several parts
│   ├── security.py          # Security headers
│   └── state.py             # StateKey: typed names in app.state
└── features/
    ├── auth/                # Login, token exchange, refresh, logout, /me
    ├── health/              # /health/live and /health/ready
    └── notes/               # The example to copy
        ├── api/             # router.py, dependencies.py, schemas/request.py, schemas/response.py
        ├── domain/          # note.py, protocols.py, service.py
        └── persistence/     # models.py, repository.py
```

## Words used here

| Word | What it means here | Example |
|---|---|---|
| Adapter | A class that does what a port says, with a real library or service | `KeycloakClient` |
| App factory | A function that builds and returns the app | `create_app()` |
| Claim | A field of a token | `sub`, the id of the user |
| Composition root | The one place that builds the objects and connects them | `bootstrap.py` |
| `core` | The part all the others share, which knows none of them | `core/exceptions.py` |
| Dependency injection | Code receives what it needs instead of building it | `Depends(get_oauth_provider)` |
| Domain | The rules of a feature, in plain Python | `features/notes/domain/` |
| Entry point | A module started from outside the code, which nothing imports | `serve.py` |
| Fake | A stand-in with no real service behind it | `InMemoryNoteRepository` |
| Feature | One folder of `features/`, on one subject | `features/notes/` |
| Flat feature | A feature with no layers, for one with no rules of its own | `features/auth/` |
| Hexagonal architecture | A project built around ports and adapters | This one |
| Import contract | A rule on imports that a tool checks | `[tool.importlinter]` in `pyproject.toml` |
| JWKS | The public keys of a realm, which Keycloak publishes so that anyone can check its signatures | `JWKSManager` |
| JWT | The format of the access token: a small JSON object and its signature, encoded as text | The token after `Bearer` |
| Layer | One height in the order of imports | `features/` and `adapters/` |
| Lifespan | The FastAPI hook that runs code before the first request and after the last one | `lifespan()` in `main.py` |
| Middleware | A wrapper around every request, which sees it on the way in and the response on the way out | `LoggingMiddleware` |
| Port | A `Protocol` that says what a service must be able to do, with no code that does it | `OAuthProvider` |
| Preflight | The `OPTIONS` request a browser sends first, to ask whether a page of another origin may call the API | `CORSMiddleware` answers it |
| Problem document | The body of an error, in the format of RFC 9457 | `core/problem_details.py` |
| Realm | The space in Keycloak that holds the users, the roles and the clients of an app | `fastapi-starter` |
| Repository | The object that reads and writes the rows of a feature | `SqlNoteRepository` |

More words on tokens and on Keycloak are in [the authentication guide](authentication.md#words).
