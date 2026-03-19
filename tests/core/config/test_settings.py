"""Tests for settings — configuration loading, URL construction, defaults.

Module under test: src/fastapi_starter/core/config/
Layer: Pure domain (Pydantic settings)

WHY these tests exist: Configuration errors are silent and catastrophic.
A wrong URL template means auth silently fails in production. We verify
computed fields produce correct URLs and security-sensitive fields are masked.
"""

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
        settings = AppSettings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.name == "fastapi_starter"
        assert settings.version == "0.1.0"
        assert settings.environment == "development"
        assert settings.debug is False

    def test_is_development_true_in_dev(self):
        """[HP] environment='development' -> is_development=True."""
        settings = AppSettings(
            environment="development",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.is_development is True

    def test_is_development_false_in_production(self):
        """[EC] environment='production' -> is_development=False."""
        settings = AppSettings(
            environment="production",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.is_development is False

    def test_is_production_true_in_production(self):
        """[HP] environment='production' -> is_production=True."""
        settings = AppSettings(
            environment="production",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.is_production is True


class TestDatabaseSettings:
    """DatabaseSettings — URL construction and pool defaults.

    WHY: The computed url property assembles the connection string.
    A wrong template = app cannot connect to the database.
    """

    def test_url_construction(self):
        """[HP] url assembles driver://user:password@host:port/name."""
        settings = DatabaseSettings(
            driver="postgresql+asyncpg",
            host="db-host",
            port=5432,
            name="mydb",
            user="myuser",
            password="secret",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.url == "postgresql+asyncpg://myuser:secret@db-host:5432/mydb"

    def test_url_safe_masks_password(self):
        """[HP] url_safe replaces password with '***'.

        WHY: url_safe is used in logs. Leaking passwords in logs
        is a security incident.
        """
        settings = DatabaseSettings(
            driver="postgresql+asyncpg",
            host="db-host",
            port=5432,
            name="mydb",
            user="myuser",
            password="super-secret-password",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert "super-secret-password" not in settings.url_safe
        assert "***" in settings.url_safe
        assert settings.url_safe == "postgresql+asyncpg://myuser:***@db-host:5432/mydb"

    def test_default_pool_settings(self):
        """[HP] Pool defaults are reasonable (pool_size=5, etc.)."""
        settings = DatabaseSettings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.pool_size == 5
        assert settings.pool_max_overflow == 10
        assert settings.pool_timeout == 5
        assert settings.pool_recycle == 1800


class TestKeycloakSettings:
    """KeycloakSettings — URL construction for OIDC endpoints.

    WHY: Four computed URLs (server, token, auth, certs) must follow
    Keycloak's exact URL patterns. A wrong URL = auth completely broken.
    """

    def test_server_url_construction(self):
        """[HP] server_url = scheme://host:port."""
        settings = KeycloakSettings(
            scheme="https",
            host="auth.example.com",
            port=443,
            realm="myrealm",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.server_url == "https://auth.example.com:443"

    def test_token_url_construction(self):
        """[HP] token_url = server_url/realms/{realm}/protocol/openid-connect/token."""
        settings = KeycloakSettings(
            scheme="http",
            host="localhost",
            port=8080,
            realm="test-realm",
            _env_file=None,  # type: ignore[call-arg]
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
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.auth_url == (
            "http://localhost:8080/realms/test-realm/protocol/openid-connect/auth"
        )

    def test_certs_url_construction(self):
        """[HP] certs_url = server_url/realms/{realm}/protocol/openid-connect/certs."""
        settings = KeycloakSettings(
            scheme="http",
            host="localhost",
            port=8080,
            realm="test-realm",
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.certs_url == (
            "http://localhost:8080/realms/test-realm/protocol/openid-connect/certs"
        )


class TestServerSettings:
    """ServerSettings — server config and trusted hosts.

    WHY: trusted_hosts drives TrustedHostMiddleware. Wrong defaults
    mean the app rejects legitimate requests or accepts malicious ones.
    """

    def test_default_trusted_hosts(self):
        """[HP] Default trusted hosts include localhost for development."""
        settings = ServerSettings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert "localhost" in settings.trusted_hosts
        assert "127.0.0.1" in settings.trusted_hosts

    def test_custom_trusted_hosts(self):
        """[HP] trusted_hosts can be overridden for production."""
        settings = ServerSettings(
            trusted_hosts=["myapp.example.com", "localhost"],
            _env_file=None,  # type: ignore[call-arg]
        )
        assert settings.trusted_hosts == ["myapp.example.com", "localhost"]

    def test_default_cors_origins(self):
        """[HP] CORS origins default to common local dev ports."""
        settings = ServerSettings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert "http://localhost:3000" in settings.cors_origins
        assert "http://localhost:5173" in settings.cors_origins
