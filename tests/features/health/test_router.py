"""Tests for health router — /health/* endpoints.

Module under test: src/fastapi_starter/features/health/router.py
Layer: HTTP endpoints (TestClient)

WHY these tests exist: Health endpoints are called by Kubernetes
(liveness/readiness probes). Wrong status codes = pods get killed
or traffic gets routed to broken instances.
"""

import pytest


class TestLiveness:
    """GET /health/live — liveness probe.

    WHY: Kubernetes uses this to detect if the process is alive.
    It must ALWAYS return 200 (no dependencies checked).
    If it returns non-200, Kubernetes restarts the pod.
    """

    async def test_returns_200(self):
        """[HP] Always returns HTTP 200."""
        pytest.skip("Not implemented yet")

    async def test_status_is_healthy(self):
        """[HP] Response body contains status='healthy'."""
        pytest.skip("Not implemented yet")

    async def test_includes_version_and_environment(self):
        """[HP] Response includes app version and environment.

        WHY: These fields help operations teams identify which version
        is deployed and in which environment.
        """
        pytest.skip("Not implemented yet")


class TestReadiness:
    """GET /health/ready — readiness probe.

    WHY: Kubernetes uses this to decide if the pod should receive traffic.
    200 = healthy (send traffic), 503 = unhealthy (stop sending traffic).
    The response must accurately reflect database AND auth status.
    """

    async def test_all_healthy_returns_200(self):
        """[HP] DB healthy + auth healthy -> 200."""
        pytest.skip("Not implemented yet")

    async def test_database_unhealthy_returns_503(self):
        """[EC] DB raises exception -> 503 with database check unhealthy."""
        pytest.skip("Not implemented yet")

    async def test_auth_unhealthy_returns_503(self):
        """[EC] Auth raises exception -> 503 with auth check unhealthy."""
        pytest.skip("Not implemented yet")

    async def test_both_unhealthy_returns_503(self):
        """[EC] Both fail -> 503, both checks show unhealthy.

        WHY: Verify that a failure in one check does not prevent
        the other check from running (no short-circuit).
        """
        pytest.skip("Not implemented yet")

    async def test_response_includes_individual_check_details(self):
        """[HP] Response body includes checks.database and checks.auth."""
        pytest.skip("Not implemented yet")

    async def test_unhealthy_check_includes_error_message(self):
        """[EC] Unhealthy check includes the error string for debugging."""
        pytest.skip("Not implemented yet")
