# FastAPI Starter 🚀

A template to kickstart FastAPI projects without configuring everything from scratch every single time.

Stack: FastAPI + PostgreSQL + Keycloak + Alembic + structlog.

## Quick Start
```bash
# 1. Clone
git clone https://github.com/yourusername/fastapi-starter.git
cd fastapi-starter

# 2. Copy and configure .env
cp .env.example .env
# Edit .env with your values (see Configuration section)

# 3. Start services
docker compose -f infra/docker-compose.yml up -d   # Keycloak
docker compose -f docker/docker-compose.yml up -d  # App PostgreSQL

# 4. Install dependencies
uv sync

# 5. Run
uv run uvicorn fastapi_starter.main:app --reload
```

Open http://localhost:8000/docs and you should see Swagger.

## What's inside

| Component | What it does |
|-----------|--------------|
| **Auth** | JWT + PKCE + Refresh Token Rotation via Keycloak |
| **Database** | Async PostgreSQL with SQLAlchemy 2.0 |
| **Migrations** | Alembic, already configured |
| **Logging** | structlog, JSON in prod, colorful in dev |
| **Health checks** | `/health/live` and `/health/ready` |
| **Config** | Pydantic Settings, everything from `.env` |
| **Exceptions** | Global handler, structured errors |

## Configuration

### Keycloak (first time setup)

1. Open http://localhost:8080
2. Login with `admin` / `admin` (or whatever you set in `infra/docker-compose.yml`)
3. Create a realm: `fastapi-starter`
4. Create a client: `fastapi-backend`
   - Client authentication: ON
   - Standard flow: ON
   - Direct access grants: OFF (only enable for testing)
   - Valid redirect URIs: `http://localhost:3000/*`, `http://localhost:8000/*`
5. Copy the client secret to `.env`
6. Create roles: `superadmin`, `admin`, `collaborator`, `user`
7. Create a test user and assign a role

### .env
```bash
# App
APP_NAME=fastapi_starter
APP_VERSION=0.1.0
APP_ENVIRONMENT=development
APP_DEBUG=true
APP_LOG_LEVEL=INFO

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Database
DATABASE_HOST=localhost
DATABASE_PORT=5433
DATABASE_NAME=appbase
DATABASE_USER=appbase
DATABASE_PASSWORD=appbase

# Keycloak
KEYCLOAK_HOST=localhost
KEYCLOAK_PORT=8080
KEYCLOAK_REALM=fastapi-starter
KEYCLOAK_CLIENT_ID=fastapi-backend
KEYCLOAK_CLIENT_SECRET=your-secret-here
```

## Project structure
```
src/fastapi_starter/
├── main.py                 # Entry point
├── core/                   # Stuff you rarely touch
│   ├── auth/               # JWT validation, dependencies
│   ├── config/             # Settings from .env
│   ├── database/           # Connection manager, Base
│   ├── logging/            # structlog setup
│   └── exceptions.py       # Custom exceptions
├── features/               # Add your stuff here
│   ├── auth/               # Login, refresh, logout endpoints
│   └── health/             # Health checks
└── alembic/                # Migrations
```

## How to use it

### Adding a feature
```bash
mkdir -p src/fastapi_starter/features/products
touch src/fastapi_starter/features/products/__init__.py
touch src/fastapi_starter/features/products/router.py
touch src/fastapi_starter/features/products/schemas.py
touch src/fastapi_starter/features/products/models.py
```

Then register the router in `main.py`:
```python
from fastapi_starter.features.products import router as products_router

app.include_router(products_router.router)
```

### Creating a migration
```bash
# 1. Create/modify your models
# 2. Import the model in alembic/env.py
# 3. Generate migration
uv run alembic revision --autogenerate -m "add_products_table"

# 4. Apply
uv run alembic upgrade head

# 5. Rollback if needed
uv run alembic downgrade -1
```

### Protecting an endpoint
```python
from fastapi_starter.core.auth import CurrentUser, AdminUser

# Any authenticated user
@router.get("/profile")
async def get_profile(user: CurrentUser):
    return user

# Admin only
@router.get("/admin/stats")
async def get_stats(user: AdminUser):
    return {"users": 100}
```

### Testing auth (without a frontend)
```bash
# Temporarily enable Direct Access Grants in Keycloak

# Get token
curl -X POST http://localhost:8080/realms/fastapi-starter/protocol/openid-connect/token \
  -d "client_id=fastapi-backend" \
  -d "client_secret=YOUR_SECRET" \
  -d "username=testuser" \
  -d "password=testpass" \
  -d "grant_type=password" | jq

# Use the token
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer ACCESS_TOKEN" | jq

# Disable Direct Access Grants after testing!
```

## Useful links

- [FastAPI docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [Alembic](https://alembic.sqlalchemy.org/)
- [Keycloak](https://www.keycloak.org/documentation)
- [structlog](https://www.structlog.org/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

## TODO (for your project)

- [ ] Rename project from `fastapi_starter` to yours
- [ ] Configure Keycloak for production
- [ ] Add your features in `features/`
- [ ] Create migrations for your models
- [ ] Set up CI/CD

---

Made with 💚 and the lovely help of ☕ and 🤖