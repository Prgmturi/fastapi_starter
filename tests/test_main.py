import pytest
from fastapi import FastAPI

from fastapi_starter.core.config import get_settings
from fastapi_starter.main import create_app


class TestCreateApp:

    def test_returns_fastapi_instance(self):
        app = create_app()

        assert isinstance(app, FastAPI)

    def test_includes_health_routes(self):
        app = create_app()

        routes = [route.path for route in app.routes]
        assert "/health/live" in routes
        assert "/health/ready" in routes

    def test_includes_auth_routes(self):
        app = create_app()

        routes = [route.path for route in app.routes]
        assert "/auth/login" in routes
        assert "/auth/token" in routes
        assert "/auth/refresh" in routes
        assert "/auth/logout" in routes
        assert "/auth/me" in routes

    def test_includes_root_route(self):
        app = create_app()

        routes = [route.path for route in app.routes]
        assert "/" in routes

    def test_docs_enabled_in_development(self, monkeypatch):
        # Arrange — force development environment
        monkeypatch.setenv("APP_ENVIRONMENT", "development")
        get_settings.cache_clear()

        # Act
        app = create_app()

        # Assert
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
        assert app.openapi_url == "/openapi.json"

        # Cleanup — always clear cache after monkeypatching settings
        get_settings.cache_clear()

    def test_docs_disabled_in_production(self, monkeypatch):
        # Arrange

        from fastapi_starter.core.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        # Act
        app = create_app()

        # Assert
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

        # Cleanup
        get_settings.cache_clear()

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
