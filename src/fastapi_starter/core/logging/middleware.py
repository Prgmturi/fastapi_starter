import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import bind_contextvars, clear_contextvars


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles HTTP request/response logging.

    For each request:
    1. Generates a UUID as request_id
    2. Binds request_id, method, path to the logging context
    3. Logs request start
    4. Executes the request handler
    5. Logs request completion with duration and status code
    6. Clears context for the next request

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

        request_id = str(uuid.uuid4())

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
        response.headers["X-Request-ID"] = request_id

        return response
