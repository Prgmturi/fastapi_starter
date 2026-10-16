"""Tests for main.py — application factory and lifespan.

Module under test: src/fastapi_starter/main.py
Layer: Application integration (composition of settings, routers, services)

WHY these tests exist: create_app() decides what the app exposes, and
lifespan() opens and closes every external connection. A leak here shows
up only in production, as sockets left open after a failed start.
"""

import os
import subprocess
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI

from fastapi_starter.core.config import AppSettings, Settings
from fastapi_starter.main import create_app, lifespan


class TestCreateApp:
    def test_returns_fastapi_instance(self, settings):
        app = create_app(settings)

        assert isinstance(app, FastAPI)

    def test_stores_settings_in_state(self, settings):
        """[HP] Dependencies and lifespan read the settings the app got."""
        app = create_app(settings)

        assert app.state.settings is settings

    def test_includes_health_routes(self, settings):
        app = create_app(settings)

        routes = [route.path for route in app.routes]
        assert "/health/live" in routes
        assert "/health/ready" in routes

    def test_includes_auth_routes(self, settings):
        app = create_app(settings)

        routes = [route.path for route in app.routes]
        assert "/auth/login" in routes
        assert "/auth/token" in routes
        assert "/auth/refresh" in routes
        assert "/auth/logout" in routes
        assert "/auth/me" in routes

    def test_includes_root_route(self, settings):
        app = create_app(settings)

        routes = [route.path for route in app.routes]
        assert "/" in routes

    def test_docs_enabled_in_development(self):
        app = create_app(Settings(app=AppSettings(environment="development")))

        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
        assert app.openapi_url == "/openapi.json"

    def test_openapi_documents_errors_as_problem_details(self, settings):
        """[HP] Every operation documents its errors as application/problem+json.

        WHY: a client generated from the schema must expect what the server
        sends. FastAPI's own 422 schema described the old {"detail": [...]}.
        """
        schema = create_app(settings).openapi()

        operations = [op for path in schema["paths"].values() for op in path.values()]
        assert operations
        for operation in operations:
            responses = operation["responses"]
            assert list(responses["default"]["content"]) == ["application/problem+json"]
            assert "422" not in responses
        problem = responses["default"]["content"]["application/problem+json"]
        assert set(problem["schema"]["required"]) == {"title", "status", "detail"}
        assert "HTTPValidationError" not in schema["components"]["schemas"]

    def test_docs_disabled_in_production(self):
        app = create_app(Settings(app=AppSettings(environment="production")))

        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    def test_without_settings_loads_them_from_environment(self, monkeypatch):
        """[HP] create_app() with no argument is the production path.

        WHY: uvicorn --factory calls create_app() with no arguments, so the
        environment must still be read there.
        """
        monkeypatch.setenv("APP_ENVIRONMENT", "production")

        app = create_app()

        assert app.state.settings.app.environment == "production"
        assert app.docs_url is None


class TestImport:
    def test_import_reads_no_configuration(self, tmp_path):
        """[EC] Importing main must not build the app.

        WHY: before --factory, main.py built the app at import time. One
        invalid variable then broke every tool that imports the package —
        pytest could not even load conftest.py. This configuration is
        invalid on purpose: the import must succeed anyway.
        """
        env = {
            **os.environ,
            "KEYCLOAK_COOKIE_NAME": "__Host-rt",
            "KEYCLOAK_COOKIE_SECURE": "false",
        }

        result = subprocess.run(
            [sys.executable, "-c", "import fastapi_starter.main"],
            cwd=tmp_path,  # no .env in this directory
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr


@patch("fastapi_starter.main.init_oauth_provider")
@patch("fastapi_starter.main.init_auth_service")
@patch("fastapi_starter.main.init_database")
class TestLifespan:
    """lifespan() — service startup and shutdown.

    WHY: every service opened at startup must be closed, both at shutdown
    and when a later service fails to start.
    """

    async def test_keycloak_adapters_share_one_http_client(
        self, init_database, init_auth_service, init_oauth_provider, settings
    ):
        """[HP] JWKS keys and token calls go through the same client."""
        app = create_app(settings)

        async with lifespan(app):
            auth_client = init_auth_service.call_args.args[2]
            oauth_client = init_oauth_provider.call_args.args[2]

            assert auth_client is oauth_client
            assert not auth_client.is_closed

    async def test_shutdown_closes_http_client_and_database(
        self, init_database, init_auth_service, init_oauth_provider, settings
    ):
        """[HP] Leaving the lifespan closes everything it opened."""
        app = create_app(settings)

        async with lifespan(app):
            http_client = init_auth_service.call_args.args[2]

        assert http_client.is_closed
        init_database.return_value.disconnect.assert_awaited_once()

    async def test_startup_failure_closes_what_was_opened(
        self, init_database, init_auth_service, init_oauth_provider, settings
    ):
        """[EC] Auth init fails -> HTTP client and database closed, error raised.

        WHY: a failed start must not leave connections open. uvicorn
        exits, but a test runner or a retry loop would keep them.
        """
        init_auth_service.side_effect = RuntimeError("JWKS unreachable")
        app = create_app(settings)

        with pytest.raises(RuntimeError, match="JWKS unreachable"):
            async with lifespan(app):
                pass

        http_client = init_auth_service.call_args.args[2]
        assert http_client.is_closed
        init_database.return_value.disconnect.assert_awaited_once()
        init_oauth_provider.assert_not_called()


class TestRootEndpoint:
    """GET / — API information."""

    async def test_returns_200_with_app_info(self, client):
        response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "name" in data
        assert "version" in data

    async def test_includes_docs_link_in_development(self, client):
        response = await client.get("/")

        data = response.json()
        assert data["docs"] == "/docs"
