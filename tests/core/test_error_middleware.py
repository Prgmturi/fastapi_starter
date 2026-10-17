"""Tests for UnhandledExceptionMiddleware — unexpected errors inside the stack.

Module under test: src/fastapi_starter/core/error_middleware.py
Layer: ASGI unit (fake app, recorded messages)

WHY these tests exist: this middleware turns a crash into the 500 the
client sees. If it sent a second response on top of one already started,
or took exceptions that are not HTTP requests, the server would break the
connection or a failed startup would go unnoticed.
"""

import json
from unittest.mock import MagicMock

import pytest

from fastapi_starter.core import error_middleware
from fastapi_starter.core.error_middleware import UnhandledExceptionMiddleware

HTTP_SCOPE = {"type": "http", "method": "GET", "path": "/orders", "headers": []}


async def receive():
    return {"type": "http.request", "body": b"", "more_body": False}


class Recorder:
    """ASGI send that keeps every message."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)


async def crash(scope, receive, send):
    raise RuntimeError("db password is hunter2")


@pytest.fixture
def logger(monkeypatch):
    """Records the middleware's log calls.

    WHY a fake: module loggers are cached on first use
    (cache_logger_on_first_use), so capture_logs cannot see them.
    """
    fake = MagicMock()
    monkeypatch.setattr(error_middleware, "logger", fake)
    return fake


class TestUnhandledExceptionMiddleware:
    async def test_passes_responses_through(self):
        """[HP] Without exceptions the app's messages reach the server as they are."""
        start = {"type": "http.response.start", "status": 201, "headers": []}
        body = {"type": "http.response.body", "body": b"ok"}

        async def app(scope, receive, send):
            await send(start)
            await send(body)

        send = Recorder()
        await UnhandledExceptionMiddleware(app)(HTTP_SCOPE, receive, send)

        assert send.messages == [start, body]

    async def test_exception_becomes_a_generic_500(self, logger):
        """[HP] An exception before the response -> one 500 problem document."""
        send = Recorder()
        await UnhandledExceptionMiddleware(crash)(HTTP_SCOPE, receive, send)

        start, body = send.messages
        assert start["status"] == 500
        assert (b"content-type", b"application/problem+json") in start["headers"]
        assert json.loads(body["body"]) == {
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred.",
        }

    async def test_exception_is_logged_with_its_traceback(self, logger):
        """[HP] The cause goes to the logs, with exc_info for the traceback."""
        await UnhandledExceptionMiddleware(crash)(HTTP_SCOPE, receive, Recorder())

        logger.error.assert_called_once()
        call = logger.error.call_args
        assert call.args == ("unhandled_exception",)
        assert call.kwargs["error_type"] == "RuntimeError"
        assert call.kwargs["path"] == "/orders"
        assert call.kwargs["method"] == "GET"
        assert call.kwargs["exc_info"] is True

    async def test_exception_after_the_response_started_goes_on(self, logger):
        """[EC] A response that already started is not replaced.

        WHY: a second http.response.start breaks the ASGI protocol. The
        exception goes on to the handler for Exception, which logs it.
        """
        start = {"type": "http.response.start", "status": 200, "headers": []}

        async def streams_then_crashes(scope, receive, send):
            await send(start)
            raise RuntimeError("stream broke")

        send = Recorder()
        with pytest.raises(RuntimeError, match="stream broke"):
            await UnhandledExceptionMiddleware(streams_then_crashes)(
                HTTP_SCOPE, receive, send
            )

        assert send.messages == [start]
        logger.error.assert_not_called()

    async def test_other_scopes_are_left_alone(self, logger):
        """[EC] Exceptions outside HTTP requests propagate unchanged.

        WHY: a 500 means nothing to lifespan or websocket. A failed startup
        must stop the app.
        """
        send = Recorder()
        with pytest.raises(RuntimeError):
            await UnhandledExceptionMiddleware(crash)(
                {"type": "lifespan"}, receive, send
            )

        assert send.messages == []
        logger.error.assert_not_called()

    async def test_other_scopes_pass_through(self):
        """[HP] Outside HTTP requests the app's messages pass as they are."""
        complete = {"type": "lifespan.startup.complete"}

        async def app(scope, receive, send):
            await send(complete)

        send = Recorder()
        await UnhandledExceptionMiddleware(app)({"type": "lifespan"}, receive, send)

        assert send.messages == [complete]
