"""Integration fixtures: a real Postgres instead of the database mocks.

Every test in this folder gets the ``integration`` marker. A plain
``pytest`` leaves them out (addopts in pyproject.toml), and
``pytest -m integration`` runs only them, against the database that
TEST_DATABASE_* describes (settings.py).
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from fastapi_starter.core.database import DatabaseManager
from fastapi_starter.core.database.dependencies import get_db_manager
from tests.integration.settings import IntegrationDatabaseSettings

HERE = Path(__file__).parent
REPOSITORY = HERE.parent.parent


# tryfirst: the marker must be there before pytest deselects by -m.
# The hook sees the items of the whole run, hence the path check.
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(HERE):
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def database_settings() -> IntegrationDatabaseSettings:
    """TEST_DATABASE_*, with a name that ends in _test."""
    return IntegrationDatabaseSettings()


@pytest.fixture(scope="session")
def migrated_database(tmp_path_factory) -> None:
    """The test database at the last migration, as CI and a deploy leave it.

    Alembic runs in a subprocess, from a folder without .env, with the
    DATABASE_* that env.py reads set to TEST_DATABASE_*. Locally no command
    is needed before the tests; in CI the migrations have run already, and
    this one changes nothing.
    """
    database = IntegrationDatabaseSettings()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(REPOSITORY / "alembic.ini")]
        + ["upgrade", "head"],
        cwd=tmp_path_factory.mktemp("alembic"),
        env={
            **os.environ,
            "DATABASE_HOST": database.host,
            "DATABASE_PORT": str(database.port),
            "DATABASE_NAME": database.name,
            "DATABASE_USER": database.user,
            "DATABASE_PASSWORD": database.password.get_secret_value(),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed:\n{result.stderr}")


@pytest.fixture
async def db_manager(database_settings) -> AsyncIterator[DatabaseManager]:
    """The real DatabaseManager, connected to the test database."""
    manager = DatabaseManager(database_settings)
    await manager.connect()
    yield manager
    await manager.disconnect()


@pytest.fixture
def app(app, db_manager):
    """The app of tests/conftest.py, with the real database.

    Only the database changes: the lifespan stays off and auth stays
    mocked. The manager goes into app.state, where get_db_manager reads it.
    """
    del app.dependency_overrides[get_db_manager]
    app.state.db_manager = db_manager
    return app
