"""Tests for health router — /health/* endpoints.

Module under test: src/fastapi_starter/features/health/router.py
Layer: HTTP endpoints (TestClient)

WHY these tests exist: Health endpoints are called by Kubernetes
(liveness/readiness probes). Wrong status codes = pods get killed
or traffic gets routed to broken instances.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from fastapi_starter.core.config import AppSettings, ServerSettings, Settings
from fastapi_starter.features.health import router as health_router_module


@pytest.fixture
def logger(monkeypatch):
    """Records the router's log calls.

    WHY a fake: module loggers are cached on first use
    (cache_logger_on_first_use), so capture_logs cannot see them.
    """
    fake = MagicMock()
    monkeypatch.setattr(health_router_module, "logger", fake)
    return fake


class TestLiveness:
    """GET /health/live — liveness probe.

    WHY: Kubernetes uses this to detect if the process is alive.
    It must ALWAYS return 200 (no dependencies checked).
    If it returns non-200, Kubernetes restarts the pod.
    """

    async def test_returns_200(self, client):
        """[HP] Always returns HTTP 200."""
        response = await client.get("/health/live")

        assert response.status_code == 200

    async def test_status_is_healthy(self, client):
        """[HP] Response body contains status='healthy'."""
        response = await client.get("/health/live")
        body = response.json()

        assert body["status"] == "healthy"

    async def test_includes_version_and_environment(self, client):
        """[HP] Response includes app version and environment.

        WHY: These fields help operations teams identify which version
        is deployed and in which environment.
        """
        response = await client.get("/health/live")
        body = response.json()

        assert "version" in body
        assert "environment" in body


class TestLivenessSettingsSource:
    """GET /health/live reports the settings of the app that answers.

    WHY: the probe used to read the global settings (get_settings), so an
    app built with create_app(settings) could report another environment.
    """

    @pytest.fixture
    def settings(self) -> Settings:
        """Overrides the root fixture: an app built for staging."""
        return Settings(
            app=AppSettings(environment="staging"),
            server=ServerSettings(trusted_hosts=["testserver"]),
        )

    async def test_reports_environment_of_this_app(self, client):
        """[HP] environment comes from app.state.settings, not from .env."""
        response = await client.get("/health/live")

        assert response.json()["environment"] == "staging"


class TestReadiness:
    """GET /health/ready — readiness probe.

    WHY: Kubernetes uses this to decide if the pod should receive traffic.
    200 = healthy (send traffic), 503 = unhealthy (stop sending traffic).
    The response must accurately reflect database AND auth status.
    """

    async def test_all_healthy_returns_200(self, client):
        """[HP] DB healthy + auth healthy -> 200."""
        response = await client.get("/health/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"

    async def test_database_unhealthy_returns_503(
        self,
        client,
        mock_db_provider,
    ):
        """[EC] DB raises exception -> 503 with database check unhealthy."""
        mock_db_provider.health_check.side_effect = RuntimeError("DB down")

        response = await client.get("/health/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["checks"]["database"]["status"] == "unhealthy"

    async def test_auth_unhealthy_returns_503(
        self,
        client,
        mock_auth_service,
    ):
        """[EC] Auth raises exception -> 503 with auth check unhealthy."""
        mock_auth_service.health_check.side_effect = RuntimeError("Auth down")

        response = await client.get("/health/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["checks"]["auth"]["status"] == "unhealthy"

    async def test_both_unhealthy_returns_503(
        self,
        client,
        mock_db_provider,
        mock_auth_service,
    ):
        """[EC] Both fail -> 503, both checks show unhealthy.

        WHY: Verify that a failure in one check does not prevent
        the other check from running (no short-circuit).
        """
        mock_db_provider.health_check.side_effect = RuntimeError("DB down")
        mock_auth_service.health_check.side_effect = RuntimeError("Auth down")

        response = await client.get("/health/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["checks"]["database"]["status"] == "unhealthy"
        assert body["checks"]["auth"]["status"] == "unhealthy"

    async def test_response_includes_individual_check_details(self, client):
        """[HP] Response body includes checks.database and checks.auth."""
        response = await client.get("/health/ready")
        body = response.json()

        assert "database" in body["checks"]
        assert "auth" in body["checks"]

    async def test_check_reporting_false_returns_503(self, client, mock_db_provider):
        """[EC] health_check() returns False -> unhealthy, like an exception.

        WHY: the protocol returns a bool. The probe used to ignore it, so a
        component that answered False was reported healthy.
        """
        mock_db_provider.health_check.return_value = False

        response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["database"]["status"] == "unhealthy"

    async def test_slow_check_times_out(
        self, client, mock_db_provider, logger, monkeypatch
    ):
        """[EC] A check slower than the timeout -> unhealthy, and the probe answers.

        WHY: a database that does not answer would hold the probe open
        until the orchestrator gives up, with no reason in the logs.
        """
        monkeypatch.setattr(health_router_module, "CHECK_TIMEOUT_SECONDS", 0.01)

        async def slow() -> bool:
            await asyncio.sleep(1)
            return True

        mock_db_provider.health_check.side_effect = slow

        response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["database"]["status"] == "unhealthy"
        logger.warning.assert_called_once_with(
            "readiness_check_failed",
            check="database",
            error="timed out after 0.01 s",
        )


class TestReadinessHidesDetails:
    """GET /health/ready tells only the status of each check.

    WHY: the endpoint needs no token. Error texts carry internal hosts,
    user names and URLs: they go to the logs, not to whoever asks.
    """

    ERROR = (
        'connection to server at "10.0.3.4", port 5432 failed: '
        'password authentication failed for user "appbase"'
    )

    async def test_body_holds_only_the_status(self, client, mock_db_provider):
        """[SEC] DB down -> the body names the failed check and nothing else."""
        mock_db_provider.health_check.side_effect = RuntimeError(self.ERROR)

        response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {
            "status": "unhealthy",
            "checks": {
                "database": {"status": "unhealthy"},
                "auth": {"status": "healthy"},
            },
        }
        assert "10.0.3.4" not in response.text

    async def test_cause_goes_to_the_log(self, client, mock_db_provider, logger):
        """[HP] The error text is logged, with the name of the check."""
        mock_db_provider.health_check.side_effect = RuntimeError(self.ERROR)

        await client.get("/health/ready")

        logger.warning.assert_called_once_with(
            "readiness_check_failed",
            check="database",
            error=f"RuntimeError: {self.ERROR}",
        )

    async def test_healthy_checks_log_nothing(self, client, logger):
        """[HP] All healthy -> no warning: the probe runs every few seconds."""
        await client.get("/health/ready")

        logger.warning.assert_not_called()
