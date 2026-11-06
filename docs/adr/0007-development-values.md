# 0007. Staging and production refuse to start on a development value

Status: accepted. Recorded on 5 November 2026, in place since 0.5.0 for production and since 0.9.0 for staging.

## Context

The project ships with values that make a clean clone run: a known database password, the public secret of the development realm, CORS on localhost. Nothing failed when one of them reached a server: staging started with the password `postgres`, an empty Keycloak client secret and CORS on localhost, and production started on the localhost frontends of development. With credentials allowed, a page on that port of a user's machine could call the API as the frontend does.

## Decision

- `Settings` runs `production_problems()` (`core/config/production.py`) in every environment but development. Staging counts too, because it is reached from outside and often holds real data.
- The check lists every problem in one error, so a deploy does not take one restart for each mistake. It names each variable to change, and never its value: settings errors hide their input (`hide_input_in_errors=True`).
- The image sets `APP_ENVIRONMENT=production`, so started without settings it refuses to start and lists what to set, instead of running as development with `/docs` open. `compose.yaml` asks for development.
- Bounds that hold in every environment stay on the fields themselves, such as the pool settings.

## Consequences

- A value left over from development stops the deploy at startup, and the log says what to change.
- A clean clone still needs no `.env`: `compose.yaml` sets development, with its own values.
- A new setting with a dangerous development value needs a line in `production_problems()`, and nothing reminds its author.
- Migrations read only `DATABASE_*`, so these checks do not run for them (`alembic/env.py`).
