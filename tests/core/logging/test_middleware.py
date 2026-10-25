"""Tests for LoggingMiddleware — the request id and the request log lines.

Module under test: src/fastapi_starter/core/logging/middleware.py
Also exercised: setup.register_middleware (CORS headers)
Layer: Infrastructure (HTTP middleware, through the real app)

WHY these tests exist: the request id ties together every log line of a
request, the response, and the proxy's own log. If it breaks, a failed
request cannot be found in the logs.
"""

import uuid

import pytest
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

REQUEST_LINES = ("request_started", "request_completed")


async def get_logged(client, headers=None):
    """GET /health/live; the response and the request id of its log lines.

    The middleware binds request_id to the context of the request: only
    merge_contextvars puts it in the captured events.
    """
    with capture_logs(processors=[merge_contextvars]) as logs:
        response = await client.get("/health/live", headers=headers)
    ids = {log["request_id"] for log in logs if log["event"] in REQUEST_LINES}
    return response, ids


class TestRequestId:
    async def test_id_from_the_proxy_is_kept(self, client):
        """[HP] A valid X-Request-ID goes into the logs and back to the client.

        WHY: with the id of the proxy, one search finds the request in the
        proxy's log and in the app's. The app always made a new one.
        """
        response, ids = await get_logged(client, {"X-Request-ID": "Req_1.a-B7"})

        assert response.headers["X-Request-ID"] == "Req_1.a-B7"
        assert ids == {"Req_1.a-B7"}

    async def test_longest_id_is_kept(self, client):
        """[EC] 64 characters is the limit, and it is allowed."""
        received = "a" * 64

        response, ids = await get_logged(client, {"X-Request-ID": received})

        assert response.headers["X-Request-ID"] == received
        assert ids == {received}

    @pytest.mark.parametrize(
        "received",
        ["a" * 65, "has space", "<script>", "a/b", ""],
        ids=["too-long", "space", "markup", "slash", "empty"],
    )
    async def test_unsafe_id_is_replaced(self, client, received):
        """[SEC] An id too long or with other characters is replaced.

        WHY: the id goes into every log line of the request and back to the
        client. Only plain, short ids pass, so a client cannot write
        arbitrary text in the logs.
        """
        response, ids = await get_logged(client, {"X-Request-ID": received})

        sent_back = response.headers["X-Request-ID"]
        assert sent_back != received
        assert uuid.UUID(sent_back)
        assert ids == {sent_back}

    async def test_id_is_made_without_the_header(self, client):
        """[HP] Without X-Request-ID the app makes one, the same everywhere."""
        response, ids = await get_logged(client)

        sent_back = response.headers["X-Request-ID"]
        assert uuid.UUID(sent_back)
        assert ids == {sent_back}


class TestCors:
    async def test_frontend_can_read_the_request_id(self, client):
        """[HP] CORS exposes X-Request-ID to a frontend on another origin.

        WHY: the browser hides from JavaScript every response header CORS
        does not expose, so the frontend could not show the id of a failed
        request to the user, or send it to support.
        """
        response = await client.get(
            "/health/live", headers={"Origin": "http://localhost:3000"}
        )

        exposed = response.headers["access-control-expose-headers"]
        assert "x-request-id" in exposed.lower()
