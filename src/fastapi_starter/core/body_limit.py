"""Request bodies larger than the limit get 413."""

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from fastapi_starter.core.problem_details import problem_response


class BodySizeLimitMiddleware:
    """Answer 413 to a request body larger than max_body_size bytes.

    uvicorn sets no limit, so without one a client can make a route read a
    body as large as the server's memory. Two checks:
    - a Content-Length over the limit gets 413 at once, the body unread;
    - a body without Content-Length (chunked) is counted while the app
      reads it. Past the limit the read stops with HTTPException(413):
      FastAPI passes an HTTPException on, while it turns any other error
      raised during body parsing into 400.

    Pure ASGI rather than BaseHTTPMiddleware: it has to wrap receive.
    """

    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size
        self.detail = f"Request body larger than {max_body_size} bytes"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if _declared_size(scope) > self.max_body_size:
            response = problem_response(413, self.detail)
            await response(scope, receive, send)
            return

        received = 0

        async def receive_within_limit() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    raise HTTPException(413, self.detail)
            return message

        await self.app(scope, receive_within_limit, send)


def _declared_size(scope: Scope) -> int:
    """Content-Length of the request; 0 when absent or not a number.

    A malformed Content-Length is the server's business: the body is
    counted anyway while it is read.
    """
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0
