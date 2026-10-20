"""Tests for database_url — the URL the engine and Alembic connect to.

Module under test: src/fastapi_starter/core/database/url.py
Layer: Pure function (settings in, SQLAlchemy URL out)

WHY these tests exist: a wrong URL means the app cannot reach the database,
and a URL printed in full leaks the password. How a password with URL
characters reaches the engine is in test_manager.py (TestConnectionUrl).
"""

from fastapi_starter.core.config.database import DatabaseSettings
from fastapi_starter.core.database.url import database_url

SETTINGS = {
    "driver": "postgresql+asyncpg",
    "host": "db-host",
    "port": 5432,
    "name": "mydb",
    "user": "myuser",
}


class TestDatabaseUrl:
    def test_parts_in_order(self):
        """[HP] driver://user:password@host:port/name."""
        url = database_url(DatabaseSettings(**SETTINGS, password="secret"))

        assert url.render_as_string(hide_password=False) == (
            "postgresql+asyncpg://myuser:secret@db-host:5432/mydb"
        )

    def test_str_and_repr_hide_the_password(self):
        """[SEC] Printing the URL by mistake does not print the password."""
        url = database_url(DatabaseSettings(**SETTINGS, password="db-secret-value"))

        assert "db-secret-value" not in str(url)
        assert "db-secret-value" not in repr(url)
        assert str(url) == "postgresql+asyncpg://myuser:***@db-host:5432/mydb"
