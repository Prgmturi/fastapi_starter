"""Where the integration tests find their Postgres.

TEST_DATABASE_* variables, exported or in .env, with the fields of
DATABASE_* (host, port, name, user, password). A prefix of their own,
because the tests create and drop tables: they must never reach the
database the app uses.

A normal module, not conftest.py, so that tests can import the class.
"""

from pydantic import field_validator
from pydantic_settings import SettingsConfigDict

from fastapi_starter.core.config.database import DatabaseSettings


class IntegrationDatabaseSettings(DatabaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEST_DATABASE_")

    @field_validator("name")
    @classmethod
    def name_ends_in_test(cls, name: str) -> str:
        # The guard against a TEST_DATABASE_NAME copied from DATABASE_NAME:
        # the tests would drop tables in the app's database.
        if not name.endswith("_test"):
            raise ValueError(
                "TEST_DATABASE_NAME must end in _test: "
                "the integration tests create and drop tables in it"
            )
        return name
