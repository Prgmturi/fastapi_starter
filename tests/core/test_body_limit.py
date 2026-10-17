"""Tests for BodySizeLimitMiddleware — 413 for request bodies over the limit.

Module under test: src/fastapi_starter/core/body_limit.py
Layer: ASGI unit (fake app, recorded messages) and HTTP (the real stack)

WHY these tests exist: uvicorn sets no limit on the request body. Without
this middleware a client can make a route read a body as large as the
server's memory.
"""

import pytest
from starlette.exceptions import HTTPException

from fastapi_starter.core.body_limit import BodySizeLimitMiddleware
from fastapi_starter.core.config import ServerSettings, Settings
from tests.test_exception_handlers import assert_problem

LIMIT = 100


def http_scope(content_length: bytes | None = None) -> dict:
    headers = [] if content_length is None else [(b"content-length", content_length)]
    return {"type": "http", "method": "POST", "path": "/upload", "headers": headers}


def body_in_chunks(*chunks: bytes):
    """receive() that hands out the body in these chunks, as a server does."""
    messages = [{"type": "http.request", "body": c, "more_body": True} for c in chunks]
    messages[-1]["more_body"] = False

    async def receive() -> dict:
        return messages.pop(0)

    return receive


class Recorder:
    """ASGI send that keeps every message."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)


async def read_body(scope, receive, send):
    """App that reads the whole body, then answers 200."""
    more_body = True
    while more_body:
        message = await receive()
        more_body = message.get("more_body", False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


class TestDeclaredSize:
    """A Content-Length over the limit is refused before the body is read."""

    async def test_content_length_over_limit_gets_413_unread(self):
        """[EC] Content-Length 101 -> 413 from the middleware, app not called."""
        called = False

        async def app(scope, receive, send):
            nonlocal called
            called = True

        send = Recorder()
        middleware = BodySizeLimitMiddleware(app, max_body_size=LIMIT)

        await middleware(http_scope(b"101"), body_in_chunks(b""), send)

        assert called is False
        assert send.messages[0]["status"] == 413

    async def test_content_length_at_limit_passes(self):
        """[HP] Exactly the limit -> the app answers."""
        send = Recorder()
        middleware = BodySizeLimitMiddleware(read_body, max_body_size=LIMIT)

        await middleware(http_scope(b"100"), body_in_chunks(b"x" * LIMIT), send)

        assert send.messages[0]["status"] == 200

    async def test_invalid_content_length_is_ignored(self):
        """[EC] Not a number -> no crash; the body is still counted."""
        send = Recorder()
        middleware = BodySizeLimitMiddleware(read_body, max_body_size=LIMIT)

        await middleware(http_scope(b"many"), body_in_chunks(b"x"), send)

        assert send.messages[0]["status"] == 200


class TestStreamedBody:
    """Without Content-Length (chunked) the body is counted while it is read."""

    async def test_chunks_over_limit_stop_the_read_with_413(self):
        """[EC] 60 + 60 bytes -> HTTPException(413) when the second chunk arrives."""
        middleware = BodySizeLimitMiddleware(read_body, max_body_size=LIMIT)

        with pytest.raises(HTTPException) as exc_info:
            await middleware(
                http_scope(), body_in_chunks(b"x" * 60, b"x" * 60), Recorder()
            )

        assert exc_info.value.status_code == 413

    async def test_chunks_up_to_limit_pass(self):
        """[HP] 50 + 50 bytes -> the app answers."""
        send = Recorder()
        middleware = BodySizeLimitMiddleware(read_body, max_body_size=LIMIT)

        await middleware(http_scope(), body_in_chunks(b"x" * 50, b"x" * 50), send)

        assert send.messages[0]["status"] == 200


class TestOtherScopes:
    async def test_lifespan_passes_untouched(self):
        """[EC] Not an HTTP request -> handed to the app as it is."""
        seen = []

        async def app(scope, receive, send):
            seen.append(scope["type"])

        middleware = BodySizeLimitMiddleware(app, max_body_size=LIMIT)

        await middleware({"type": "lifespan"}, body_in_chunks(b""), Recorder())

        assert seen == ["lifespan"]


class TestThroughTheApp:
    """The real middleware stack: the 413 is a problem document with headers.

    WHY: FastAPI turns an error raised while it parses the body into 400.
    The 413 must survive that, and get CORS and X-Request-ID like any
    other error.
    """

    @pytest.fixture
    def settings(self) -> Settings:
        """Overrides the root fixture: a 100-byte limit."""
        return Settings(
            server=ServerSettings(trusted_hosts=["testserver"], max_body_size=LIMIT)
        )

    @pytest.fixture(autouse=True)
    def upload_route(self, app):
        @app.post("/upload")
        async def upload(payload: dict[str, str]) -> dict[str, int]:
            return {"keys": len(payload)}

    async def test_declared_body_over_limit(self, client):
        """[EC] JSON body of 200 bytes -> 413 with CORS and X-Request-ID."""
        response = await client.post(
            "/upload",
            json={"data": "x" * 200},
            headers={"Origin": "http://localhost:3000"},
        )

        body = assert_problem(response, 413)
        assert body["detail"] == "Request body larger than 100 bytes"
        assert "x-request-id" in response.headers
        assert response.headers["access-control-allow-origin"] == (
            "http://localhost:3000"
        )

    async def test_streamed_body_over_limit(self, client):
        """[EC] Chunked body, no Content-Length -> 413, not FastAPI's 400."""

        async def chunks():
            yield b'{"data": "'
            yield b"x" * 200
            yield b'"}'

        response = await client.post(
            "/upload", content=chunks(), headers={"Content-Type": "application/json"}
        )

        assert_problem(response, 413)

    async def test_body_within_limit(self, client):
        """[HP] Small body -> the route answers."""
        response = await client.post("/upload", json={"a": "b"})

        assert response.status_code == 200
        assert response.json() == {"keys": 1}
