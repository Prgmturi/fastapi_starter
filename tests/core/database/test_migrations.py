"""Tests for the helpers of alembic/env.py — finding the models, the guard.

Module under test: src/fastapi_starter/core/database/migrations.py
Layer: Database infrastructure, no database needed

WHY these tests exist: a model reaches Base.metadata only when its module
is imported, and Alembic reads Base.metadata. With the imports written by
hand in alembic/env.py, a forgotten one left its model out of the migration
autogenerate wrote, without an error (tried on 27 October 2026: with one
model imported and one forgotten, autogenerate created only the first).
"""

import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table

import fastapi_starter.features
from fastapi_starter.core.database import Base
from fastapi_starter.core.database.migrations import (
    import_models,
    refuse_empty_autogenerate,
)

# The files of a fake package: models modules at two depths, and modules
# that must not be imported, so they fail if they are
FAKE_PACKAGE = {
    "__init__.py": "",
    "a/__init__.py": "",
    "a/models.py": "",
    "b/__init__.py": "",
    "b/persistence/__init__.py": "",
    "b/persistence/models.py": "",
    "c/__init__.py": "",
    "c/service.py": "raise RuntimeError('only models modules are imported')",
    "c/old_models.py": "raise RuntimeError('only models modules are imported')",
}


@pytest.fixture
def fake_package(tmp_path, monkeypatch) -> Iterator[str]:
    """A package on sys.path with FAKE_PACKAGE in it, removed afterwards."""
    name = f"fake_features_{uuid.uuid4().hex}"
    for file, content in FAKE_PACKAGE.items():
        path = tmp_path / name / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    for module in [module for module in sys.modules if module.startswith(name)]:
        del sys.modules[module]


class TestImportModels:
    def test_imports_every_models_module(self, fake_package):
        """[HP] models.py at any depth is imported, and its name returned."""
        package = __import__(fake_package)

        found = import_models(package)

        assert found == [
            f"{fake_package}.a.models",
            f"{fake_package}.b.persistence.models",
        ]
        assert all(name in sys.modules for name in found)

    def test_imports_nothing_else(self, fake_package):
        """[EC] Other modules stay unimported: each would raise if it were."""
        import_models(__import__(fake_package))

        assert f"{fake_package}.c.service" not in sys.modules
        assert f"{fake_package}.c.old_models" not in sys.modules


class TestRefuseEmptyAutogenerate:
    """The guard against an autogenerate with no model.

    WHY: with no table in the metadata, autogenerate compares "nothing" with
    the database and writes a drop_table for every table: a plausible
    migration that deletes production.
    """

    def test_no_table_stops(self):
        """[EC] Empty metadata -> an error that says what to do."""
        with pytest.raises(RuntimeError, match="Base.metadata has no table"):
            refuse_empty_autogenerate(MetaData())

    def test_a_table_passes(self):
        """[HP] Metadata with a table -> nothing happens."""
        metadata = MetaData()
        Table("things", metadata, Column("id", Integer, primary_key=True))

        refuse_empty_autogenerate(metadata)


def test_finds_the_model_of_notes():
    """[HP] On the real features: the notes table reaches Base.metadata."""
    found = import_models(fastapi_starter.features)

    assert found == ["fastapi_starter.features.notes.persistence.models"]
    assert "notes" in Base.metadata.tables


def test_alembic_env_uses_both():
    """[HP] alembic/env.py calls the two helpers on the features package.

    WHY: a helper nobody calls protects nothing. tests/test_alembic.py runs
    env.py itself; this test names the calls.
    """
    env = (Path(__file__).parents[3] / "alembic" / "env.py").read_text()

    assert "import_models(fastapi_starter.features)" in env
    assert "refuse_empty_autogenerate(target_metadata)" in env
