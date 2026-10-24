"""The integration tests accept only a database whose name ends in _test.

Module under test: tests/integration/settings.py
Layer: test setup

WHY: the integration tests create and drop tables. Pointed at the app's
database by mistake, for example with a TEST_DATABASE_NAME copied from
DATABASE_NAME, they would delete real data.
"""

import pytest
from pydantic import ValidationError

from tests.integration.settings import IntegrationDatabaseSettings


class TestIntegrationDatabaseSettings:
    def test_name_without_test_suffix_is_refused(self):
        """[EC] The app's database name -> refused before any connection."""
        with pytest.raises(ValidationError, match="must end in _test"):
            IntegrationDatabaseSettings(name="appbase")

    def test_name_with_test_suffix_is_accepted(self):
        """[HP] A name ending in _test is used as given."""
        settings = IntegrationDatabaseSettings(name="appbase_test")

        assert settings.name == "appbase_test"

    def test_reads_test_database_variables_only(self, monkeypatch):
        """[HP] TEST_DATABASE_NAME is read, DATABASE_NAME is not.

        WHY: DATABASE_* is the app's database. Read here, it would make
        the tests run against it.
        """
        monkeypatch.setenv("DATABASE_NAME", "appbase")
        monkeypatch.setenv("TEST_DATABASE_NAME", "appbase_test")

        assert IntegrationDatabaseSettings().name == "appbase_test"
