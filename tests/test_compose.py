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
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pydantic
import pytest
import yaml

from fastapi_starter.core.config import KeycloakSettings, Settings

ROOT = Path(__file__).parent.parent
COMPOSE = ROOT / "compose.yaml"
COMPOSE_PROD = ROOT / "compose.prod.yaml"
DEV_REALM = ROOT / "docker" / "keycloak" / "realm-dev.json"
REALM_IMPORT_DIR = "/opt/keycloak/data/import/"
RELEASED_IMAGE = "ghcr.io/prgmturi/fastapi_starter"
# A variable the server's .env must set: ${NAME:?message}
REQUIRED = re.compile(r"\$\{\w+:\?[^}]+\}")


@dataclass
class Tag:
    """A Compose tag such as !reset or !override, with its value."""

    name: str
    value: object


class ComposeLoader(yaml.SafeLoader):
    """yaml.safe_load, plus the tags Compose adds to YAML."""


def construct_tag(loader: ComposeLoader, suffix: str, node: yaml.Node) -> Tag:
    if isinstance(node, yaml.SequenceNode):
        return Tag(suffix, loader.construct_sequence(node, deep=True))
    if isinstance(node, yaml.MappingNode):
        return Tag(suffix, loader.construct_mapping(node, deep=True))
    return Tag(suffix, loader.construct_scalar(node))


ComposeLoader.add_multi_constructor("!", construct_tag)


def services() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]


def prod() -> dict:
    return yaml.load(COMPOSE_PROD.read_text(), Loader=ComposeLoader)


def prod_env(service: str) -> dict:
    return prod()["services"][service].get("environment", {})


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
            for section, entries in yaml.load(path.read_text(), ComposeLoader).items()
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


class TestProduction:
    """compose.prod.yaml over compose.yaml: the stack on a server.

    WHY: compose.yaml holds development values only: Keycloak in start-dev
    with a public realm, every port open on the host, passwords written in
    the file. Measured on 25 October 2026 on the development stack:
    Keycloak's metrics and health answered on port 9000 without a login.
    """

    def test_api_and_migrations_run_the_released_image(self):
        """[HP] No build on the server: the image of the current release."""
        version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
            "version"
        ]

        for name in ("api", "migrate"):
            service = prod()["services"][name]
            assert service["build"] == Tag("reset", "null")
            assert service["image"] == f"${{APP_IMAGE:-{RELEASED_IMAGE}:{version}}}"

    def test_every_password_and_secret_is_required(self):
        """[SEC] Each password or secret of compose.yaml comes from the server.

        WHY: compose.yaml writes development values. A variable missing on
        the server must stop the deploy, not start it with those.
        """
        written = [
            f"{name}.{key}"
            for name, service in services().items()
            for key in service.get("environment", {})
            if "PASSWORD" in key or "SECRET" in key
            if not REQUIRED.fullmatch(prod_env(name).get(key, ""))
        ]

        assert written == []

    def test_the_api_runs_in_production(self):
        """[HP] The checks of core/config/production.py apply."""
        assert prod_env("api")["APP_ENVIRONMENT"] == "production"
        for key in ("KEYCLOAK_PUBLIC_URL", "KEYCLOAK_ALLOWED_REDIRECT_URIS"):
            assert REQUIRED.fullmatch(prod_env("api")[key]), key
        for key in ("SERVER_TRUSTED_HOSTS", "SERVER_CORS_ORIGINS"):
            assert REQUIRED.fullmatch(prod_env("api")[key]), key

    def test_keycloak_runs_in_production_mode_behind_the_proxy(self):
        """[SEC] start, no imported realm, plain HTTP only from the TLS proxy."""
        keycloak = prod()["services"]["keycloak"]
        env = keycloak["environment"]

        assert keycloak["command"] == Tag("override", ["start"])
        assert keycloak["volumes"] == Tag("reset", [])
        assert env["KC_HTTP_ENABLED"] == "true"
        assert env["KC_PROXY_HEADERS"] == "xforwarded"
        assert env["KC_HOSTNAME"] == prod_env("api")["KEYCLOAK_PUBLIC_URL"]

    def test_the_console_has_an_address_of_its_own(self):
        """[SEC] The administration console answers on 127.0.0.1 only.

        WHY: with KC_HOSTNAME_ADMIN the console no longer needs the public
        name, so the proxy can refuse /admin/ (docs/production.md).
        """
        admin_url = prod_env("keycloak")["KC_HOSTNAME_ADMIN"]

        assert admin_url.startswith("${KEYCLOAK_ADMIN_URL:-http://127.0.0.1:")

    def test_ports_only_on_the_loopback_of_the_server(self):
        """[SEC] Every port compose.yaml publishes is closed or on 127.0.0.1.

        WHY: a published port is open on every interface of the server,
        beside the proxy and its TLS.
        """
        published = [name for name, service in services().items() if "ports" in service]
        ports = {name: prod()["services"][name]["ports"] for name in published}

        assert published
        assert [
            name
            for name, entries in ports.items()
            if not isinstance(entries, Tag)
            or not all(entry.startswith("127.0.0.1:") for entry in entries.value)
        ] == []

    def test_proxy_headers_trusted_only_from_the_stack(self):
        """[SEC] uvicorn and Keycloak trust X-Forwarded-* from the stack's network.

        WHY: the proxy on the host reaches the containers from the gateway of
        that network; anyone else could choose the client address.
        """
        subnet = prod()["networks"]["default"]["ipam"]["config"][0]["subnet"]

        assert prod_env("api")["SERVER_FORWARDED_ALLOW_IPS"] == f'["{subnet}"]'
        assert prod_env("keycloak")["KC_PROXY_TRUSTED_ADDRESSES"] == subnet

    def test_logs_are_rotated(self):
        """[HP] Every service keeps at most a few files of logs.

        WHY: Docker's json-file driver never rotates by itself, and a server
        runs for months.
        """
        logging = {
            name: prod()["services"][name].get("logging", {}) for name in services()
        }

        assert [
            name
            for name, log in logging.items()
            if "max-size" not in log.get("options", {})
        ] == []
