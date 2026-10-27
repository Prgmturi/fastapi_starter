# 0005. SQLAlchemy is part of core; a feature with rules keeps it behind a port

Status: accepted. Recorded on 27 October 2026.

## Context

Features need a database, transactions that match requests, and migrations. Swapping Postgres for another database is not a goal of the template; testing business rules without a database is.

## Decision

- SQLAlchemy 2 with asyncpg lives in `core/database/`: `DatabaseManager` (engine, pool limits, pre-ping, timeouts), `DbSession` (one session and one transaction per request, committed when the route returns and before the response, so a failed commit answers 500), `BaseRepository` (pages always in primary key order).
- SQLAlchemy is not an adapter to swap: a simple feature uses `DbSession` and a repository on `BaseRepository` directly, as the README shows.
- A feature with rules of its own keeps SQLAlchemy in its `persistence/` layer, behind a port of its domain. `features/notes/` does: `NoteRepository` in `domain/protocols.py`, `SqlNoteRepository` in `persistence/repository.py`, and the domain in plain Python, tested with a repository kept in memory.
- Alembic writes and runs the migrations. `alembic/env.py` finds the models by name, every module called `models` under `features/`, and reads only `DATABASE_*`. Indexes and constraints are named by the convention of `core/database/base.py`. CI runs every migration up, compares them with the models (`alembic check`), then down and up again.

## Consequences

- Two ways to reach the database, and the README says when each fits: flat for a feature with no rules, three layers when the rules deserve tests without a database.
- The feature with a port maps rows to domain objects and back: more code, in exchange for a pure domain.
- The naming convention is fixed since the first migration, of `notes`: changing it now renames constraints that exist.
