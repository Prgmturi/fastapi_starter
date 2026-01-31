import time
import uuid
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware che gestisce il logging per ogni richiesta HTTP.

    Per ogni richiesta:
    1. Genera un UUID come request_id
    2. Lega request_id, method, path al contesto di logging
    3. Logga l'inizio della richiesta
    4. Esegue la richiesta
    5. Logga la fine con durata e status code
    6. Pulisce il contesto per la prossima richiesta

    Example output:
        {"event": "request_started", "request_id": "abc-123", "method": "GET",
        "path": "/users"}
        {"event": "request_completed", "request_id": "abc-123", "status_code": 200,
        "duration_ms": 45}
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        # Pulisci contesto da richieste precedenti
        # Importante in ambiente async dove i worker sono riutilizzati
        clear_contextvars()

        # Genera request_id univoco
        request_id = str(uuid.uuid4())

        # Lega informazioni al contesto
        # Tutti i log da qui in poi avranno questi campi
        bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        # Ottieni logger
        logger = structlog.get_logger()

        # Timestamp di inizio
        start_time = time.perf_counter()

        # Log inizio richiesta
        logger.info(
            "request_started",
            query_params=dict(request.query_params) if request.query_params else None,
        )

        response = await call_next(request)

        # Calcola durata
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Log completamento
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        # Aggiungi request_id all'header della risposta
        response.headers["X-Request-ID"] = request_id

        return response
