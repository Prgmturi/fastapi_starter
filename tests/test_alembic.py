"""Tests for alembic/env.py — what a migration reads and what it refuses.

Module under test: alembic/env.py
Layer: Deployment tooling (Alembic in a subprocess, no database)

WHY these tests exist: env.py runs only when someone runs Alembic, so no
other test executes it. Two of its rules matter in production: a migration
needs the database settings and nothing else, and autogenerate without
models stops before it writes a migration that drops every table.
"""

import os
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
VERSIONS = REPOSITORY / "alembic" / "versions"


def alembic(*args: str, cwd: Path, **variables: str) -> subprocess.CompletedProcess:
    """Run the repository's Alembic, from a directory without .env."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(REPOSITORY / "alembic.ini"), *args],
        cwd=cwd,
        env={**os.environ, **variables},
        capture_output=True,
        text=True,
        check=False,
    )


class TestMigrationSettings:
    def test_production_migration_needs_only_the_database(self, tmp_path):
        """[EC] APP_ENVIRONMENT=production and DATABASE_* only -> it runs.

        WHY: env.py loaded every setting, so production refused to migrate
        without the Keycloak secret, the redirect URIs and the trusted
        hosts, which a migration never uses. --sql writes the SQL instead of
        connecting, so no database is needed.
        """
        result = alembic(
            "upgrade",
            "head",
            "--sql",
            cwd=tmp_path,
            APP_ENVIRONMENT="production",
            DATABASE_PASSWORD="db-password-from-the-vault",
        )

        assert result.returncode == 0, result.stderr
        assert "alembic_version" in result.stdout


class TestAutogenerateGuard:
    def test_without_models_stops_before_connecting(self, tmp_path):
        """[EC] No model imported -> autogenerate stops, no migration written.

        WHY: with an empty Base.metadata Alembic sees "the database has
        every table, the code none" and writes a drop_table for each. The
        port refuses connections: an error from it would mean env.py tried
        to connect before stopping.
        """
        before = sorted(VERSIONS.iterdir())

        result = alembic(
            "revision",
            "--autogenerate",
            "-m",
            "should not be written",
            cwd=tmp_path,
            DATABASE_HOST="127.0.0.1",
            DATABASE_PORT="1",
        )

        assert result.returncode != 0
        assert "Base.metadata" in result.stderr
        assert "drop_table" in result.stderr
        assert "Connect" not in result.stderr
        assert sorted(VERSIONS.iterdir()) == before
