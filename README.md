# fastapi-starter

![Python](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi&logoColor=white)
![CI](https://github.com/Prgmturi/fastapi_starter/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/Prgmturi/fastapi_starter)
![Tests](https://img.shields.io/badge/tests-206%20passed-brightgreen?logo=pytest&logoColor=white)

A backend template built with FastAPI to learn and apply real architectural patterns — hexagonal architecture, SOLID, clean separation of concerns. Useful as a starting point for future projects: the infrastructure is already there, you just add features.

## What's in here

| Layer | What it does |
|---|---|
| **Auth** | Full OAuth2 + PKCE flow via Keycloak. JWT validation through JWKS with key rotation. Refresh tokens in HttpOnly cookies. |
| **Architecture** | Hexagonal (Ports & Adapters). Core logic talks only to protocols — swap Keycloak for Auth0 without touching `AuthService`. |
| **Database** | Async PostgreSQL with SQLAlchemy 2.0. Connection pooling, session lifecycle, base repository pattern. |
| **Config** | Pydantic Settings, layered by domain (`AppSettings`, `DatabaseSettings`, etc.), loaded from `.env`. |
| **Logging** | structlog. JSON in production with service metadata, colorized in development. Request IDs on every log line. |
| **Errors** | Domain exceptions (`NotFoundError`, `UnauthorizedError`, ...) with global handlers. No library exceptions leak to the client. |
| **Testing** | 206 tests. Fully async, no real database or auth server needed. |

## Architecture

The project is split into two layers that don't bleed into each other:

```
core/       ← infrastructure: auth, database, config, logging, exceptions
features/   ← business logic: your endpoints go here
```

`core/` defines behavior through `Protocol` classes (ports). Concrete implementations (adapters) live alongside them but are only wired together in one place — `setup.py`. This means `AuthService` has no idea what PyJWT is, `JWKSManager` has no idea what SQLAlchemy is, and adding a feature doesn't require touching infrastructure code.

```
src/fastapi_starter/
├── main.py                  # App factory + lifespan
├── setup.py                 # Composition root — the only place that knows everything
├── core/
│   ├── auth/                # JWT validation, JWKS, Keycloak claim extraction
│   ├── config/              # Settings by domain, loaded from .env
│   ├── database/            # Async engine, session factory, base repository
│   ├── logging/             # structlog config + request logging middleware
│   ├── exceptions.py        # Domain exception hierarchy
│   └── protocols.py         # Cross-cutting contracts
└── features/
    ├── auth/                # Login, token exchange, refresh, logout, /me
    └── health/              # /health/live and /health/ready
```

## Getting started

**Prerequisites:** Python 3.13, Docker, [uv](https://docs.astral.sh/uv/)

```bash
# 1. Clone
git clone https://github.com/Prgmturi/fastapi_starter.git
cd fastapi-starter

# 2. Configure
cp .env.example .env
# Fill in KEYCLOAK_CLIENT_SECRET after completing the Keycloak setup below

# 3. Start infrastructure
docker compose -f infra/docker-compose.yml up -d    # Keycloak + its database
docker compose -f docker/docker-compose.yaml up -d  # App database (port 5433)

# 4. Install and run
uv sync
uv run alembic upgrade head
uv run uvicorn fastapi_starter.main:app --reload
```

Open http://localhost:8000/docs.

### Keycloak setup (first time)

1. Open http://localhost:8080 → log in with `admin` / `admin`
2. Create realm: `fastapi-starter`
3. Create client: `fastapi-backend`
   - Client authentication: **ON**
   - Standard flow: **ON**
   - Valid redirect URIs: `http://localhost:*`
4. Copy the client secret → `.env` → `KEYCLOAK_CLIENT_SECRET`
5. Create roles: `superadmin`, `admin`, `collaborator`, `user`
6. Create a test user and assign a role

## Authentication flow

```
GET  /auth/login    → returns authorization URL (PKCE)
POST /auth/token    → exchanges code for tokens; refresh token set as HttpOnly cookie
POST /auth/refresh  → refreshes access token using the cookie
POST /auth/logout   → revokes refresh token, clears cookie
GET  /auth/me       → decodes bearer JWT via JWKS, returns User
```

JWT validation uses `JWKSManager`, which caches Keycloak's public keys with a configurable TTL and retries on key rotation automatically.

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
from fastapi_starter.core.auth.dependencies import CurrentUser, AdminUser, require_roles
from fastapi_starter.core.auth.schemas import RoleEnum

# Any authenticated user
@router.get("/profile")
async def profile(user: CurrentUser): ...

# Admin or superadmin only
@router.get("/stats")
async def stats(user: AdminUser): ...

# Custom role check — import Annotated, User, Depends alongside the rest
@router.delete("/users/{id}")
async def delete_user(user: Annotated[User, Depends(require_roles([RoleEnum.SUPERADMIN]))]): ...
```

## Running tests

```bash
uv run pytest                              # all 206 tests
uv run pytest tests/core/auth/            # a module
uv run pytest tests/core/auth/test_service.py::test_validate_token  # one test
uv run pytest --cov=src/fastapi_starter   # with coverage
```

Tests are fully async and use `AsyncMock` stubs — no real database or Keycloak instance needed. The root `conftest.py` provides fixtures for the app, HTTP client, mock services, and sample users at different role levels.

## Database migrations

```bash
uv run alembic revision --autogenerate -m "add products table"
uv run alembic upgrade head
uv run alembic downgrade -1
```

Define models by subclassing `Base` from `core/database/manager.py`. Import them in `alembic/env.py` before running autogenerate.

## Configuration reference

All settings are read from `.env`. See `.env.example` for the full list.

Two separate PostgreSQL instances:
- **App DB** — port `5433` (`docker/docker-compose.yaml`)
- **Keycloak DB** — internal to `infra/docker-compose.yml`

Key environment variables:

```bash
APP_ENVIRONMENT=development        # development | staging | production
APP_LOG_LEVEL=INFO
DATABASE_PORT=5433
KEYCLOAK_CLIENT_SECRET=...         # required
SERVER_CORS_ORIGINS=["http://localhost:3000"]
```

`/docs`, `/redoc`, and `/openapi.json` are only available when `APP_ENVIRONMENT=development`.

## Stack

- [FastAPI](https://fastapi.tiangolo.com/) 0.128
- [SQLAlchemy](https://docs.sqlalchemy.org/en/20/) 2.0 (async)
- [Alembic](https://alembic.sqlalchemy.org/)
- [Keycloak](https://www.keycloak.org/) via [python-keycloak](https://python-keycloak.readthedocs.io/)
- [structlog](https://www.structlog.org/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [uv](https://docs.astral.sh/uv/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)

---

Built by [Prgmturi](https://github.com/Prgmturi) · [Claude](https://claude.ai) was an excellent teammate 🤖
