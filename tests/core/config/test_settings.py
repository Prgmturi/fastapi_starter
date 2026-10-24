"""Tests for settings — configuration loading, URL construction, defaults.

Module under test: src/fastapi_starter/core/config/
Layer: Pure domain (Pydantic settings)

WHY these tests exist: Configuration errors are silent and catastrophic.
A wrong URL template means auth silently fails in production. We verify
computed fields produce correct URLs and security-sensitive fields are masked.
"""

import importlib.metadata

import pydantic
import pytest

from fastapi_starter.core.config import Settings
from fastapi_starter.core.config import app as app_module
from fastapi_starter.core.config.app import AppSettings
from fastapi_starter.core.config.database import DatabaseSettings
from fastapi_starter.core.config.keycloak import KeycloakSettings
from fastapi_starter.core.config.server import ServerSettings


class TestAppSettings:
    """AppSettings — application metadata and environment detection.

    WHY: is_development/is_production control docs visibility and
    debug behavior. Wrong detection = docs exposed in production.
    """

    def test_default_values(self):
        """[HP] Defaults are development-friendly."""
        settings = AppSettings()
        assert settings.name == "fastapi_starter"
        assert settings.environment == "development"
        assert settings.debug is False

    def test_version_is_the_installed_package(self):
        """[HP] /health/live and OpenAPI show the version that runs.

        WHY: the default was "0.1.0" in the code and in .env.example, while
        release-please bumps pyproject.toml: from 0.2.0 on, every release
        still answered 0.1.0.
        """
        assert AppSettings().version == importlib.metadata.version("fastapi_starter")

    def test_version_unknown_without_an_installed_package(self, monkeypatch):
        """[EC] Source on PYTHONPATH, never installed: "unknown", not a crash."""

        def not_installed(name: str) -> str:
            raise importlib.metadata.PackageNotFoundError(name)

        monkeypatch.setattr(app_module, "package_version", not_installed)

        assert AppSettings().version == "unknown"

    def test_app_version_still_overrides(self, monkeypatch):
        """[HP] APP_VERSION, for a build that wants its own label."""
        monkeypatch.setenv("APP_VERSION", "1.2.3-rc1")

        assert AppSettings().version == "1.2.3-rc1"

    def test_is_development_true_in_dev(self):
        """[HP] environment='development' -> is_development=True."""
        settings = AppSettings(environment="development")
        assert settings.is_development is True

    def test_is_development_false_in_production(self):
        """[EC] environment='production' -> is_development=False."""
        settings = AppSettings(environment="production")
        assert settings.is_development is False

    def test_is_production_true_in_production(self):
        """[HP] environment='production' -> is_production=True."""
        settings = AppSettings(environment="production")
        assert settings.is_production is True

    @pytest.mark.parametrize("given", ["debug", "Debug", "DEBUG"])
    def test_log_level_any_case(self, given):
        """[HP] APP_LOG_LEVEL=debug works like DEBUG."""
        assert AppSettings(log_level=given).log_level == "DEBUG"

    def test_log_level_read_from_the_environment(self, monkeypatch):
        """[HP] APP_LOG_LEVEL, as written in .env."""
        monkeypatch.setenv("APP_LOG_LEVEL", "warning")

        assert AppSettings().log_level == "WARNING"

    @pytest.mark.parametrize("given", ["verbose", "WARN ", "root"])
    def test_log_level_typo_refused(self, given):
        """[EC] An unknown level stops the startup.

        WHY: getattr(logging, level, logging.INFO) turned a typo into INFO
        without a word, and "root" into a Logger object.
        """
        with pytest.raises(pydantic.ValidationError, match="DEBUG"):
            AppSettings(log_level=given)


class TestDatabaseSettings:
    """DatabaseSettings — pool defaults.

    The URL is built in core/database/url.py (tests/core/database/test_url.py).
    """

    def test_default_pool_settings(self):
        """[HP] Pool defaults are reasonable (pool_size=5, etc.)."""
        settings = DatabaseSettings()
        assert settings.pool_size == 5
        assert settings.pool_max_overflow == 10
        assert settings.pool_timeout == 5
        assert settings.pool_recycle == 1800

    def test_default_timeouts(self):
        """[HP] 5 s to connect, 30 s per query.

        WHY: asyncpg has no query limit and waits 60 s for a connection.
        """
        settings = DatabaseSettings()
        assert settings.connect_timeout == 5
        assert settings.command_timeout == 30

    def test_timeouts_read_from_the_environment(self, monkeypatch):
        """[HP] DATABASE_CONNECT_TIMEOUT and DATABASE_COMMAND_TIMEOUT."""
        monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT", "2.5")
        monkeypatch.setenv("DATABASE_COMMAND_TIMEOUT", "120")

        settings = DatabaseSettings()

        assert (settings.connect_timeout, settings.command_timeout) == (2.5, 120)

    @pytest.mark.parametrize("field", ["connect_timeout", "command_timeout"])
    def test_timeouts_must_be_positive(self, field):
        """[EC] 0 would make every connection or query fail at once."""
        with pytest.raises(pydantic.ValidationError, match=field):
            DatabaseSettings(**{field: 0})

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            # SQLAlchemy reads 0 as "no limit": 20 connections asked, 20 opened
            ("pool_size", 0),
            # ...and a negative size lowers the limit: -1 + 10 overflow = 9
            ("pool_size", -1),
            # -1 is SQLAlchemy's "no overflow limit"
            ("pool_max_overflow", -1),
            # A full pool would fail every request at once instead of waiting
            ("pool_timeout", 0),
            # Every checkout would open a new connection: no pool left
            ("pool_recycle", 0),
        ],
    )
    def test_pool_setting_out_of_range_refused(self, field, value):
        """[EC] A value SQLAlchemy reads in a surprising way -> refused at startup."""
        with pytest.raises(pydantic.ValidationError, match=field):
            DatabaseSettings(**{field: value})

    def test_smallest_pool_accepted(self):
        """[HP] One connection and no overflow is a valid, if small, pool."""
        settings = DatabaseSettings(pool_size=1, pool_max_overflow=0)

        assert (settings.pool_size, settings.pool_max_overflow) == (1, 0)


class TestKeycloakSettings:
    """KeycloakSettings — OIDC endpoint URLs and which tokens are accepted.

    WHY: Four computed URLs (server, token, auth, certs) must follow
    Keycloak's exact URL patterns. A wrong URL = auth completely broken.
    """

    def test_allowed_clients_default_to_client_id(self):
        """[HP] No list given -> only tokens issued to client_id are accepted."""
        settings = KeycloakSettings(client_id="orders-api")

        assert settings.allowed_clients == ["orders-api"]

    def test_allowed_clients_read_as_json_list(self, monkeypatch):
        """[HP] KEYCLOAK_ALLOWED_CLIENTS is a JSON list, like SERVER_CORS_ORIGINS."""
        monkeypatch.setenv("KEYCLOAK_ALLOWED_CLIENTS", '["orders-api","web"]')

        assert KeycloakSettings().allowed_clients == ["orders-api", "web"]

    def test_audience_empty_by_default(self):
        """[HP] Empty audience: the decoder does not check aud."""
        assert KeycloakSettings().audience == ""

    def test_server_url_construction(self):
        """[HP] server_url = scheme://host:port."""
        settings = KeycloakSettings(
            scheme="https",
            host="auth.example.com",
            port=443,
            realm="myrealm",
        )
        assert settings.server_url == "https://auth.example.com:443"

    def test_token_url_construction(self):
        """[HP] token_url = server_url/realms/{realm}/protocol/openid-connect/token."""
        settings = KeycloakSettings(
            scheme="http",
            host="localhost",
            port=8080,
            realm="test-realm",
        )
        assert settings.token_url == (
            "http://localhost:8080/realms/test-realm/protocol/openid-connect/token"
        )

    def test_auth_url_construction(self):
        """[HP] auth_url = server_url/realms/{realm}/protocol/openid-connect/auth."""
        settings = KeycloakSettings(
            scheme="http",
            host="localhost",
            port=8080,
            realm="test-realm",
        )
        assert settings.auth_url == (
            "http://localhost:8080/realms/test-realm/protocol/openid-connect/auth"
        )

    def test_browser_and_issuer_use_the_public_url(self):
        """[HP] Login redirect and issuer: public. Tokens and keys: internal.

        WHY: in Docker the API reaches Keycloak at keycloak:8080, a name the
        browser cannot resolve, while Keycloak signs tokens with its public
        address. With one URL for both, the login redirect pointed the
        browser at keycloak:8080.
        """
        settings = KeycloakSettings(
            scheme="http",
            host="keycloak",
            port=8080,
            realm="shop",
            public_url="https://auth.example.com",
        )

        assert settings.auth_url == (
            "https://auth.example.com/realms/shop/protocol/openid-connect/auth"
        )
        assert settings.issuer == "https://auth.example.com/realms/shop"
        assert settings.token_url == (
            "http://keycloak:8080/realms/shop/protocol/openid-connect/token"
        )
        assert settings.certs_url == (
            "http://keycloak:8080/realms/shop/protocol/openid-connect/certs"
        )

    def test_without_public_url_everything_is_internal(self):
        """[HP] KEYCLOAK_PUBLIC_URL unset: development does not change."""
        settings = KeycloakSettings(realm="shop")

        assert settings.issuer == "http://localhost:8080/realms/shop"
        assert settings.auth_url == (
            "http://localhost:8080/realms/shop/protocol/openid-connect/auth"
        )

    def test_public_url_read_from_the_environment(self, monkeypatch):
        """[HP] KEYCLOAK_PUBLIC_URL, a trailing slash dropped."""
        monkeypatch.setenv("KEYCLOAK_PUBLIC_URL", "https://auth.example.com/")

        assert KeycloakSettings(realm="shop").issuer == (
            "https://auth.example.com/realms/shop"
        )

    def test_public_url_needs_a_scheme(self):
        """[EC] "auth.example.com" alone would make a relative redirect."""
        with pytest.raises(pydantic.ValidationError, match="http:// or https://"):
            KeycloakSettings(public_url="auth.example.com")

    def test_certs_url_construction(self):
        """[HP] certs_url = server_url/realms/{realm}/protocol/openid-connect/certs."""
        settings = KeycloakSettings(
            scheme="http",
            host="localhost",
            port=8080,
            realm="test-realm",
        )
        assert settings.certs_url == (
            "http://localhost:8080/realms/test-realm/protocol/openid-connect/certs"
        )


class TestSecrets:
    """Database password and Keycloak client secret.

    WHY: settings reach logs and tracebacks through repr() and model_dump().
    As plain strings, both secrets were printed in full, and the password a
    second time inside the database URL.
    """

    @pytest.fixture
    def settings(self) -> Settings:
        return Settings(
            database=DatabaseSettings(password="db-secret-value"),
            keycloak=KeycloakSettings(client_secret="kc-secret-value"),
        )

    @pytest.mark.parametrize("secret", ["db-secret-value", "kc-secret-value"])
    def test_secret_not_in_repr_or_dumps(self, settings, secret):
        """[SEC] repr, model_dump and JSON of the whole settings hide it."""
        assert secret not in repr(settings)
        assert secret not in str(settings.model_dump())
        assert secret not in settings.model_dump_json()

    def test_secrets_readable_on_request(self, settings):
        """[HP] get_secret_value() gives the value to the code that needs it."""
        assert settings.database.password.get_secret_value() == "db-secret-value"
        assert settings.keycloak.client_secret.get_secret_value() == "kc-secret-value"


class TestProductionChecks:
    """With APP_ENVIRONMENT=production, development values stop the startup.

    WHY: the app started in production with debug on, Keycloak on http, an
    empty client secret, the password "postgres" and the development
    trusted hosts. Each change below starts from a valid production
    environment (production_env) and breaks one thing.
    """

    def test_valid_production_environment_starts(self, production_env):
        """[HP] Real values everywhere: no error."""
        assert Settings().app.environment == "production"

    def test_development_defaults_still_start(self):
        """[HP] The checks never block development."""
        assert Settings().app.environment == "development"

    @pytest.mark.parametrize(
        ("change", "named"),
        [
            ({"APP_DEBUG": "true"}, "APP_DEBUG"),
            ({"KEYCLOAK_PUBLIC_URL": "http://auth.example.com"}, "KEYCLOAK_PUBLIC_URL"),
            # Unset, the public address is KEYCLOAK_SCHEME://..., http by default
            ({"KEYCLOAK_PUBLIC_URL": None}, "KEYCLOAK_PUBLIC_URL"),
            ({"KEYCLOAK_CLIENT_SECRET": ""}, "KEYCLOAK_CLIENT_SECRET"),
            (
                {"KEYCLOAK_CLIENT_SECRET": "your-client-secret-here"},
                "KEYCLOAK_CLIENT_SECRET",
            ),
            # __Host- already demands Secure: the check matters for other names
            (
                {"KEYCLOAK_COOKIE_NAME": "rt", "KEYCLOAK_COOKIE_SECURE": "false"},
                "KEYCLOAK_COOKIE_SECURE",
            ),
            (
                {"KEYCLOAK_ALLOWED_REDIRECT_URIS": None},
                "KEYCLOAK_ALLOWED_REDIRECT_URIS",
            ),
            ({"DATABASE_PASSWORD": None}, "DATABASE_PASSWORD"),
            ({"DATABASE_PASSWORD": "appbase_secret_change_me"}, "DATABASE_PASSWORD"),
            # echo logs every query with its values: personal data in the logs
            ({"DATABASE_ECHO": "true"}, "DATABASE_ECHO"),
            ({"SERVER_CORS_ORIGINS": '["*"]'}, "SERVER_CORS_ORIGINS"),
            ({"SERVER_TRUSTED_HOSTS": None}, "SERVER_TRUSTED_HOSTS"),
            ({"SERVER_TRUSTED_HOSTS": '["*"]'}, "SERVER_TRUSTED_HOSTS"),
        ],
        ids=[
            "debug",
            "public-url-http",
            "public-url-unset",
            "secret-empty",
            "secret-example",
            "cookie-not-secure",
            "redirect-uris-unset",
            "db-password-default",
            "db-password-example",
            "db-echo",
            "cors-any-origin",
            "trusted-hosts-local",
            "trusted-hosts-any",
        ],
    )
    def test_development_value_refused(
        self, production_env, monkeypatch, change, named
    ):
        """[SEC] One development value -> an error that names its variable."""
        for name, value in change.items():
            if value is None:
                monkeypatch.delenv(name)
            else:
                monkeypatch.setenv(name, value)

        with pytest.raises(pydantic.ValidationError) as exc_info:
            Settings()

        assert named in str(exc_info.value)

    def test_every_problem_in_one_error(self, monkeypatch):
        """[HP] All development values at once -> one error listing them all.

        WHY: one error per restart would turn a deploy into a guessing game.
        """
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        monkeypatch.setenv("APP_DEBUG", "true")

        with pytest.raises(pydantic.ValidationError) as exc_info:
            Settings()

        message = str(exc_info.value)
        for named in (
            "APP_DEBUG",
            "KEYCLOAK_PUBLIC_URL",
            "KEYCLOAK_CLIENT_SECRET",
            "KEYCLOAK_ALLOWED_REDIRECT_URIS",
            "DATABASE_PASSWORD",
            "SERVER_TRUSTED_HOSTS",
        ):
            assert named in message

    def test_error_shows_no_secret(self, production_env, monkeypatch):
        """[SEC] The error names variables, never their values."""
        monkeypatch.setenv("APP_DEBUG", "true")

        with pytest.raises(pydantic.ValidationError) as exc_info:
            Settings()

        assert production_env["DATABASE_PASSWORD"] not in str(exc_info.value)
        assert production_env["KEYCLOAK_CLIENT_SECRET"] not in str(exc_info.value)


class TestServerSettings:
    """ServerSettings — server config and trusted hosts.

    WHY: trusted_hosts drives TrustedHostMiddleware. Wrong defaults
    mean the app rejects legitimate requests or accepts malicious ones.
    """

    def test_default_trusted_hosts(self):
        """[HP] Default trusted hosts include localhost for development."""
        settings = ServerSettings()
        assert "localhost" in settings.trusted_hosts
        assert "127.0.0.1" in settings.trusted_hosts

    def test_custom_trusted_hosts(self):
        """[HP] trusted_hosts can be overridden for production."""
        settings = ServerSettings(trusted_hosts=["myapp.example.com", "localhost"])
        assert settings.trusted_hosts == ["myapp.example.com", "localhost"]

    def test_default_cors_origins(self):
        """[HP] CORS origins default to common local dev ports."""
        settings = ServerSettings()
        assert "http://localhost:3000" in settings.cors_origins
        assert "http://localhost:5173" in settings.cors_origins

    def test_default_max_body_size(self):
        """[HP] Request bodies are limited to 64 KiB by default."""
        assert ServerSettings().max_body_size == 64 * 1024

    def test_max_body_size_must_be_positive(self):
        """[EC] 0 would answer 413 to every request with a body."""
        with pytest.raises(pydantic.ValidationError):
            ServerSettings(max_body_size=0)
