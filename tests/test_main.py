"""Tests for main.py — application factory and lifespan.

Module under test: src/fastapi_starter/main.py
Layer: Application integration (composition of settings, routers, services)

WHY these tests exist: create_app() decides what the app exposes, and
lifespan() opens and closes every external connection. A leak here shows
up only in production, as sockets left open after a failed start.
"""

import asyncio
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

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

    # Since FastAPI 0.137 app.routes is internal: included routers stay
    # whole, so it is a tree, not a list of routes. url_path_for finds a
    # route by its name (the function's) anywhere in the tree.
    def test_includes_health_routes(self, settings):
        app = create_app(settings)

        assert app.url_path_for("liveness") == "/health/live"
        assert app.url_path_for("readiness") == "/health/ready"

    def test_includes_auth_routes(self, settings):
        app = create_app(settings)

        assert app.url_path_for("get_login_url") == "/auth/login"
        assert app.url_path_for("exchange_token") == "/auth/token"
        assert app.url_path_for("refresh_token") == "/auth/refresh"
        assert app.url_path_for("logout") == "/auth/logout"
        assert app.url_path_for("get_me") == "/auth/me"

    def test_includes_root_route(self, settings):
        app = create_app(settings)

        assert app.url_path_for("root") == "/"

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

    def test_docs_disabled_in_production(self, production_env):
        app = create_app(Settings())

        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    def test_without_settings_loads_them_from_environment(self, production_env):
        """[HP] create_app() with no argument is the production path.

        WHY: uvicorn --factory calls create_app() with no arguments, so the
        environment must still be read there.
        """
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


@pytest.fixture
def main_logger(monkeypatch) -> MagicMock:
    """Records the log calls of main.py.

    WHY a fake: module loggers are cached on first use
    (cache_logger_on_first_use), so capture_logs cannot see them.
    """
    fake = MagicMock()
    monkeypatch.setattr("fastapi_starter.main.logger", fake)
    return fake


def logged_events(logger: MagicMock) -> list[str]:
    return [call.args[0] for call in logger.info.call_args_list]


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

    async def test_cancelled_while_serving_closes_everything(
        self, init_database, init_auth_service, init_oauth_provider, settings
    ):
        """[EC] Cancelled at yield -> HTTP client and database closed.

        WHY: uvicorn does this when Ctrl+C arrives during a slow startup:
        it lets the startup finish, skips the shutdown and cancels the
        lifespan where it waits, at yield. The code after yield never ran.
        """
        app = create_app(settings)
        serving = asyncio.Event()

        async def serve() -> None:
            async with lifespan(app):
                serving.set()
                await asyncio.Event().wait()  # until cancelled

        task = asyncio.create_task(serve())
        await serving.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert init_auth_service.call_args.args[2].is_closed
        init_database.return_value.disconnect.assert_awaited_once()

    async def test_cancelled_during_startup_closes_what_was_opened(
        self, init_database, init_auth_service, init_oauth_provider, settings
    ):
        """[EC] Cancelled while auth starts -> HTTP client and database closed.

        WHY: CancelledError is not an Exception, so "except Exception"
        let it through: a runner that gives up on a slow startup, with a
        timeout for example, left the database and the HTTP client open.
        """
        waiting_for_keycloak = asyncio.Event()

        async def keycloak_never_answers(*args) -> None:
            waiting_for_keycloak.set()
            await asyncio.Event().wait()

        init_auth_service.side_effect = keycloak_never_answers
        app = create_app(settings)

        async def start() -> None:
            async with lifespan(app):
                pass

        task = asyncio.create_task(start())
        await waiting_for_keycloak.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert init_auth_service.call_args.args[2].is_closed
        init_database.return_value.disconnect.assert_awaited_once()

    async def test_started_is_logged_once_the_services_run(
        self,
        init_database,
        init_auth_service,
        init_oauth_provider,
        settings,
        main_logger,
    ):
        """[HP] started, stopping, stopped: in this order, around the yield."""
        app = create_app(settings)

        async with lifespan(app):
            assert logged_events(main_logger) == ["application_started"]

        assert logged_events(main_logger) == [
            "application_started",
            "application_stopping",
            "application_stopped",
        ]

    async def test_failed_startup_never_logs_started(
        self,
        init_database,
        init_auth_service,
        init_oauth_provider,
        settings,
        main_logger,
    ):
        """[EC] Auth init fails -> no application_started in the logs.

        WHY: "started" followed by an error made a failed start look like
        a crash of a running app.
        """
        init_auth_service.side_effect = RuntimeError("JWKS unreachable")
        app = create_app(settings)

        with pytest.raises(RuntimeError):
            async with lifespan(app):
                pass

        assert "application_started" not in logged_events(main_logger)


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
