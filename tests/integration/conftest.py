"""Integration fixtures: a real Postgres instead of the database mocks.

Every test in this folder gets the ``integration`` marker. A plain
``pytest`` leaves them out (addopts in pyproject.toml), and
``pytest -m integration`` runs only them, against the database that
TEST_DATABASE_* describes (settings.py).
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from fastapi_starter.core.database import DatabaseManager
from fastapi_starter.core.database.dependencies import get_db_manager
from tests.integration.settings import IntegrationDatabaseSettings

HERE = Path(__file__).parent


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
