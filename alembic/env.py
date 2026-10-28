import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import fastapi_starter.features
from fastapi_starter.core.config import DatabaseSettings
from fastapi_starter.core.database import Base, database_url
from fastapi_starter.core.database.migrations import (
    import_models,
    refuse_empty_autogenerate,
)

# Alembic Config object
config = context.config

# Setup logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Every module called models under features, found by its name: a model
# whose module nobody imports is missing from Base.metadata, so from every
# migration, without an error.
import_models(fastapi_starter.features)
target_metadata = Base.metadata

if getattr(config.cmd_opts, "autogenerate", False):
    refuse_empty_autogenerate(target_metadata)

# Only the database settings: a migration uses nothing else. Loading every
# setting made production refuse to migrate without the Keycloak secret, the
# redirect URIs and the trusted hosts.
database = DatabaseSettings()


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates SQL script without connecting to database.
    """
    url = database_url(database)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode with async engine.
    """
    connectable = create_async_engine(
        database_url(database),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
