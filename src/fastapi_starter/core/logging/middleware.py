import re
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import bind_contextvars, clear_contextvars

REQUEST_ID_HEADER = "X-Request-ID"

# An id that comes with the request goes into every log line of it and back
# to the client: only short ids of plain characters are kept.
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def request_id_for(request: Request) -> str:
    """The X-Request-ID the request came with, if safe; otherwise a new one.

    The proxy sets it, so its log and the app's share the id.
    """
    received = request.headers.get(REQUEST_ID_HEADER)
    if received is not None and SAFE_REQUEST_ID.fullmatch(received):
        return received
    return str(uuid.uuid4())


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles HTTP request/response logging.

    For each request:
    1. Clears the logging context of the previous request
    2. Takes the request id from X-Request-ID, or generates a UUID
    3. Binds request_id, method, path to the logging context
    4. Logs request start
    5. Executes the request handler
    6. Logs request completion with duration and status code
    7. Sends the request id back in X-Request-ID

    Example output:
        {"event": "request_started", "request_id": "abc-123", "method": "GET",
        "path": "/users"}
        {"event": "request_completed", "request_id": "abc-123", "status_code": 200,
        "duration_ms": 45}
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Clear context from previous requests.
        # Important in async environments where workers are reused.
        clear_contextvars()

        request_id = request_id_for(request)

        # Bind info to context - all subsequent logs will include these fields
        bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        logger = structlog.get_logger()

        start_time = time.perf_counter()

        logger.info(
            "request_started",
            query_params=dict(request.query_params) if request.query_params else None,
        )

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        # Add request_id to response headers
        response.headers[REQUEST_ID_HEADER] = request_id

        return response
