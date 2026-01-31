"""Tests for health router — /health/* endpoints.

Module under test: src/fastapi_starter/features/health/router.py
Layer: HTTP endpoints (TestClient)

WHY these tests exist: Health endpoints are called by Kubernetes
(liveness/readiness probes). Wrong status codes = pods get killed
or traffic gets routed to broken instances.
"""


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

    async def test_unhealthy_check_includes_error_message(
        self,
        client,
        mock_db_provider,
    ):
        """[EC] Unhealthy check includes the error string for debugging."""
        mock_db_provider.health_check.side_effect = RuntimeError("connection refused")

        response = await client.get("/health/ready")
        body = response.json()

        assert "error" in body["checks"]["database"]
        assert "connection refused" in body["checks"]["database"]["error"]
