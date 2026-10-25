import logging
import sys

import structlog
from structlog.typing import FilteringBoundLogger, Processor

from fastapi_starter.core.logging.processors import (
    clean_event_dict,
    drop_color_message_key,
    make_service_info_processor,
)

# uvicorn sets these up before it calls the app factory: each one gets its
# own handler and text format, and keeps its records from the root logger.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def get_processors(
    environment: str, app_name: str = "", version: str = ""
) -> list[Processor]:
    """Processors that fill in an event, all but the renderer.

    The same ones run for structlog's loggers and for the records of the
    standard logging module (uvicorn, SQLAlchemy, httpx).
    """
    if environment == "development":
        # Development: minimal, colorized, human-readable output.
        # No service info or callsite - keep it clean for local work.
        return [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            clean_event_dict,
            drop_color_message_key,
        ]
    else:
        # Production/Staging: JSON with full metadata for log aggregation.
        return [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            make_service_info_processor(app_name, version, environment),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                ]
            ),
            clean_event_dict,
            drop_color_message_key,
            structlog.processors.format_exc_info,
        ]


def get_renderer(environment: str) -> Processor:
    """The last processor: it turns the event into the line written."""
    if environment == "development":
        return structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )
    return structlog.processors.JSONRenderer()


def configure_logging(
    environment: str = "development",
    log_level: str = "INFO",
    app_name: str = "",
    version: str = "",
) -> None:
    """
    Configure the logging system for the entire application.

    Must be called ONCE at application startup, before any logging. The
    records of the libraries, uvicorn's included, get the same format.

    Args:
        environment: "development", "staging", or "production"
        log_level: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
        app_name: Application name (injected into production logs)
        version: Application version (injected into production logs)

    Example:
    ```python
        from fastapi_starter.core.logging import configure_logging

        configure_logging(
            environment="development",
            log_level="DEBUG",
        )
    ```
    """
    # getattr(logging, name) would turn a typo into a default, or "root"
    # into a Logger: only real level names pass
    level = logging.getLevelNamesMapping().get(log_level.upper())
    if level is None:
        raise ValueError(f"unknown log level {log_level!r}")

    # Build processors for the environment
    processors = get_processors(environment, app_name, version)
    renderer = get_renderer(environment)

    # Configure structlog
    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard Python logging (for external libraries): their
    # records go through the same processors and renderer as structlog's,
    # so uvicorn, sqlalchemy, httpx, etc. write lines in the same format.
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            # First: the logger name comes from the record, which
            # clean_event_dict removes from the event.
            foreign_pre_chain=[structlog.stdlib.add_logger_name, *processors],
            processors=[renderer],
        )
    )

    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # uvicorn configured its loggers before calling the app factory: take
    # their handlers away, so their records reach the root handler.
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # request_completed says what uvicorn's access line says, with the
    # request id and the duration, and the access line also carries the
    # query string, which can hold personal data. Delete this line to have
    # it back.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Silence overly verbose libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """
    Get a configured logger.

    Args:
        name: Optional logger name (e.g. module name).
              If not specified, structlog determines it automatically.

    Returns:
        Ready-to-use logger

    Example:
    ```python
        from fastapi_starter.core.logging import get_logger

        logger = get_logger(__name__)
        logger.info("user_created", user_id=123)
    ```
    """
    if name:
        return structlog.get_logger(name)  # type: ignore[no-any-return]
    return structlog.get_logger()  # type: ignore[no-any-return]
