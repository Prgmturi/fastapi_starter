"""Tests for LoggingMiddleware — the request id and the request log lines.

Module under test: src/fastapi_starter/core/logging/middleware.py
Also exercised: setup.register_middleware (CORS headers, quiet probes)
Layer: Infrastructure (HTTP middleware, through the real app)

WHY these tests exist: the request id ties together every log line of a
request, the response, and the proxy's own log. If it breaks, a failed
request cannot be found in the logs.
"""

import logging
import uuid

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from fastapi_starter.core.logging import LoggingMiddleware

REQUEST_LINES = ("request_started", "request_completed")


async def get_logged(client, path="/", headers=None):
    """GET path; the response and the request lines it logged.

    The middleware binds request_id to the context of the request: only
    merge_contextvars puts it in the captured events.
    """
    with capture_logs(processors=[merge_contextvars]) as logs:
        response = await client.get(path, headers=headers)
    return response, [log for log in logs if log["event"] in REQUEST_LINES]


def ids_of(lines):
    return {line["request_id"] for line in lines}


@pytest.fixture
def debug_level(app):
    """APP_LOG_LEVEL=DEBUG, set after create_app has configured logging."""
    previous = structlog.get_config()["wrapper_class"]
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
    )
    yield
    structlog.configure(wrapper_class=previous)


class TestRequestId:
    async def test_id_from_the_proxy_is_kept(self, client):
        """[HP] A valid X-Request-ID goes into the logs and back to the client.

        WHY: with the id of the proxy, one search finds the request in the
        proxy's log and in the app's. The app always made a new one.
        """
        response, lines = await get_logged(
            client, headers={"X-Request-ID": "Req_1.a-B7"}
        )

        assert response.headers["X-Request-ID"] == "Req_1.a-B7"
        assert ids_of(lines) == {"Req_1.a-B7"}

    async def test_longest_id_is_kept(self, client):
        """[EC] 64 characters is the limit, and it is allowed."""
        received = "a" * 64

        response, lines = await get_logged(client, headers={"X-Request-ID": received})

        assert response.headers["X-Request-ID"] == received
        assert ids_of(lines) == {received}

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
        response, lines = await get_logged(client, headers={"X-Request-ID": received})

        sent_back = response.headers["X-Request-ID"]
        assert sent_back != received
        assert uuid.UUID(sent_back)
        assert ids_of(lines) == {sent_back}

    async def test_id_is_made_without_the_header(self, client):
        """[HP] Without X-Request-ID the app makes one, the same everywhere."""
        response, lines = await get_logged(client)

        sent_back = response.headers["X-Request-ID"]
        assert uuid.UUID(sent_back)
        assert ids_of(lines) == {sent_back}


class TestRequestLines:
    """What request_started says about a request, and what it leaves out."""

    async def test_query_string_is_not_logged(self, client):
        """[SEC] The query string stays out of the logs.

        WHY: it can hold personal data or tokens, and request_started wrote
        it whole, as query_params.
        """
        _, lines = await get_logged(
            client, "/?email=mario.rossi@example.com&token=s3cr3t"
        )

        assert lines
        assert "mario.rossi" not in str(lines)
        assert "s3cr3t" not in str(lines)

    async def test_client_and_user_agent_are_logged(self, client):
        """[HP] request_started says who made the request, and with what.

        WHY: in a security incident the first questions are where the
        requests came from and which program sent them.
        """
        _, lines = await get_logged(client, headers={"User-Agent": "probe/1.0"})

        started = lines[0]
        assert started["event"] == "request_started"
        assert started["client_ip"] == "127.0.0.1"
        assert started["user_agent"] == "probe/1.0"

    async def test_forwarded_for_alone_changes_nothing(self, client):
        """[SEC] The app does not read X-Forwarded-For itself.

        WHY: any client can send the header. Only uvicorn applies it, and
        only to connections from the addresses in FORWARDED_ALLOW_IPS.
        """
        _, lines = await get_logged(client, headers={"X-Forwarded-For": "203.0.113.7"})

        assert lines[0]["client_ip"] == "127.0.0.1"

    @pytest.mark.parametrize(
        ("trusted", "logged"),
        [("127.0.0.1", "203.0.113.7"), ("10.0.0.0/8", "127.0.0.1")],
        ids=["from-the-trusted-proxy", "from-another-address"],
    )
    async def test_ip_forwarded_by_the_proxy(self, app, trusted, logged):
        """[HP] Behind a trusted proxy, client_ip is the client's address.

        WHY: uvicorn applies X-Forwarded-For only to connections from the
        addresses in FORWARDED_ALLOW_IPS, 127.0.0.1 by default. In a
        container the proxy has another address: without the setting every
        line shows the proxy's. httpx connects from 127.0.0.1.
        """
        behind_proxy = ProxyHeadersMiddleware(app, trusted_hosts=trusted)
        async with AsyncClient(
            transport=ASGITransport(app=behind_proxy), base_url="http://testserver"
        ) as client:
            _, lines = await get_logged(
                client, headers={"X-Forwarded-For": "203.0.113.7"}
            )

        assert lines[0]["client_ip"] == logged


class TestProbes:
    """Docker's HEALTHCHECK and the orchestrator call the probes all day."""

    @pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
    async def test_probe_lines_are_not_written_at_info(self, client, path):
        """[HP] At INFO a probe writes no request lines.

        WHY: the HEALTHCHECK alone wrote two lines every 30 seconds, 5,760 a
        day, between the lines that matter.
        """
        _, lines = await get_logged(client, path)

        assert lines == []

    @pytest.mark.usefixtures("debug_level")
    async def test_probe_lines_are_debug(self, client):
        """[HP] The probe lines are still there, at DEBUG."""
        _, lines = await get_logged(client, "/health/live")

        assert [line["log_level"] for line in lines] == ["debug", "debug"]

    async def test_only_paths_under_the_prefix_are_quiet(self, client):
        """[EC] /healthz is not under /health/: its lines stay at INFO."""
        _, lines = await get_logged(client, "/healthz")

        assert [line["log_level"] for line in lines] == ["info", "info"]


class BrokenMiddleware(BaseHTTPMiddleware):
    """Any middleware between LoggingMiddleware and the error middleware."""

    async def dispatch(self, request, call_next):
        raise RuntimeError("middleware bug")


@pytest.fixture
def app_with_broken_middleware():
    """LoggingMiddleware outside, a middleware that raises right inside it.

    The error middleware only covers what is closer to the routes, so an
    exception raised here crosses LoggingMiddleware.
    """
    application = FastAPI()

    @application.get("/")
    async def root():
        return {}

    application.add_middleware(BrokenMiddleware)
    application.add_middleware(LoggingMiddleware)
    return application


class TestFailingMiddleware:
    async def test_request_completed_is_logged_as_500(self, app_with_broken_middleware):
        """[EC] A request whose middleware raises still gets request_completed.

        WHY: the request had request_started and then nothing, so its
        status and duration were missing. Starlette answers it with a 500.
        """
        async with AsyncClient(
            transport=ASGITransport(
                app=app_with_broken_middleware, raise_app_exceptions=False
            ),
            base_url="http://testserver",
        ) as client:
            response, lines = await get_logged(client)

        assert response.status_code == 500
        completed = [line for line in lines if line["event"] == "request_completed"]
        assert [line["status_code"] for line in completed] == [500]
        assert completed[0]["duration_ms"] >= 0

    async def test_the_exception_goes_on(self, app_with_broken_middleware):
        """[EC] LoggingMiddleware writes its line and lets the exception go.

        WHY: the handler registered for Exception must still get it, to log
        the traceback and answer 500.
        """
        async with AsyncClient(
            transport=ASGITransport(app=app_with_broken_middleware),
            base_url="http://testserver",
        ) as client:
            with pytest.raises(RuntimeError, match="middleware bug"):
                await client.get("/")


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
