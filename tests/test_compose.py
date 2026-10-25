"""Tests for compose.yaml, the whole stack started with docker compose up.

WHY these tests exist: from a clean clone docker compose up answered "no
configuration file provided". Starting the app took three .env files, two
compose files and six steps by hand in Keycloak's console. And the two
compose files fixed the names of their containers, networks and volumes,
so a second project made from this template would have used the first
one's database volume. tests/e2e/ logs in through the running stack.
"""

import json
import re
from pathlib import Path

import pydantic
import pytest
import yaml

from fastapi_starter.core.config import KeycloakSettings, Settings

ROOT = Path(__file__).parent.parent
COMPOSE = ROOT / "compose.yaml"
DEV_REALM = ROOT / "docker" / "keycloak" / "realm-dev.json"
REALM_IMPORT_DIR = "/opt/keycloak/data/import/"


def services() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]


def realm() -> dict:
    return json.loads(DEV_REALM.read_text())


def backend_client() -> dict:
    """The client of the realm that the API logs users in with."""
    client_id = KeycloakSettings().client_id
    return next(c for c in realm()["clients"] if c["clientId"] == client_id)


def compose_files() -> list[Path]:
    """Every compose file of the repository."""
    return [
        path
        for pattern in ("compose*.yaml", "*/docker-compose.y*ml")
        for path in ROOT.glob(pattern)
    ]


def env_example(name: str) -> str:
    match = re.search(rf"^{name}=(.*)$", (ROOT / ".env.example").read_text(), re.M)
    assert match is not None, name
    return match.group(1)


class TestStack:
    def test_one_file_starts_everything(self):
        """[HP] API, migrations, Postgres, Keycloak and its Postgres."""
        assert set(services()) == {"api", "migrate", "db", "keycloak", "keycloak-db"}

    def test_no_fixed_names(self):
        """[HP] Compose derives every name from the project.

        WHY: a fixed volume name is shared by every project that uses it,
        so a second clone, or a second project made from the template,
        would start on the first one's database.
        """
        fixed = [
            f"{path.name}: {section} {key}"
            for path in compose_files()
            for section, entries in yaml.safe_load(path.read_text()).items()
            if isinstance(entries, dict)
            for key, entry in entries.items()
            if isinstance(entry, dict) and {"container_name", "name"} & set(entry)
        ]

        assert compose_files()
        assert fixed == []

    def test_api_starts_after_migrations_and_keycloak(self):
        """[HP] The API waits for the schema and for Keycloak's keys.

        WHY: the startup fetches Keycloak's signing keys and fails if
        Keycloak is not ready; requests need the tables of the migrations.
        """
        assert services()["api"]["depends_on"] == {
            "db": {"condition": "service_healthy"},
            "migrate": {"condition": "service_completed_successfully"},
            "keycloak": {"condition": "service_healthy"},
        }
        assert services()["migrate"]["command"] == ["alembic", "upgrade", "head"]
        assert services()["migrate"]["depends_on"] == {
            "db": {"condition": "service_healthy"}
        }


class TestDevRealm:
    """The realm Keycloak imports, and the API settings that match it."""

    def test_keycloak_imports_the_realm(self):
        """[HP] start-dev with --import-realm, and the file in the import folder."""
        keycloak = services()["keycloak"]

        assert keycloak["command"] == ["start-dev", "--import-realm"]
        assert any(
            volume.startswith("./docker/keycloak/realm-dev.json:" + REALM_IMPORT_DIR)
            for volume in keycloak["volumes"]
        )

    def test_realm_and_client_are_the_api_defaults(self):
        """[HP] The realm and the client the API uses unless told otherwise."""
        assert realm()["realm"] == KeycloakSettings().realm
        assert backend_client()["publicClient"] is False

    def test_api_has_the_client_secret_of_the_realm(self):
        """[HP] One development secret: the realm's, the API's, .env.example's."""
        secret = backend_client()["secret"]

        assert services()["api"]["environment"]["KEYCLOAK_CLIENT_SECRET"] == secret
        assert env_example("KEYCLOAK_CLIENT_SECRET") == secret

    def test_issuer_is_the_address_of_the_browser(self):
        """[HP] Tokens name the address the browser uses, the one the API expects.

        WHY: the API reaches Keycloak at http://keycloak:8080, the browser at
        localhost. Keycloak names KC_HOSTNAME as issuer; the API compares it
        with KEYCLOAK_PUBLIC_URL and answers 401 Invalid issuer otherwise
        (measured with a real Keycloak on 20 October 2026).
        """
        keycloak = services()["keycloak"]["environment"]
        api = services()["api"]["environment"]

        assert keycloak["KC_HOSTNAME"] == api["KEYCLOAK_PUBLIC_URL"]
        assert keycloak["KC_HOSTNAME_BACKCHANNEL_DYNAMIC"] == "true"
        assert api["KEYCLOAK_HOST"] == "keycloak"

    def test_production_refuses_the_dev_secret(self, production_env, monkeypatch):
        """[SEC] The secret of the dev realm is public: production stops on it."""
        monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", backend_client()["secret"])

        with pytest.raises(pydantic.ValidationError) as exc_info:
            Settings()

        assert "KEYCLOAK_CLIENT_SECRET" in str(exc_info.value)
