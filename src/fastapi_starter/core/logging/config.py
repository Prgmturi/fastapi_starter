import logging
import sys

import structlog
from structlog.types import Processor

from fastapi_starter.core.logging.processors import (
    add_service_info,
    clean_event_dict,
    drop_color_message_key,
)


def get_processors(environment: str) -> list[Processor]:
    # Shared processors for all environments.
    # Order matters!
    shared_processors: list[Processor] = [
        # 1. Merge context variables (request_id, etc.)
        structlog.contextvars.merge_contextvars,
        # 2. Add log level ("info", "error", etc.)
        structlog.processors.add_log_level,
        # 3. Add ISO-formatted timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # 4. Add service info (name, version, environment)
        add_service_info,
        # 5. Remove internal keys
        clean_event_dict,
        # 6. Remove uvicorn's color_message key
        drop_color_message_key,
    ]

    if environment == "development":
        # Development: colorized, human-readable output
        return shared_processors + [
            # Add callsite info (filename, line number, function)
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                ]
            ),
            # Colorized console renderer
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]
    else:
        # Production/Staging: JSON output
        return shared_processors + [
            # Format exceptions as strings
            structlog.processors.format_exc_info,
            # JSON output
            structlog.processors.JSONRenderer(),
        ]


def configure_logging(
    environment: str = "development",
    log_level: str = "INFO",
) -> None:
    """
    Configure the logging system for the entire application.

    Must be called ONCE at application startup, before any logging.

    Args:
        environment: "development", "staging", or "production"
        log_level: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"

    Example:
    ```python
        from fastapi_starter.core.logging import configure_logging

        configure_logging(
            environment="development",
            log_level="DEBUG",
        )
    ```
    """
    # Convert string to numeric level
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Build processors for the environment
    processors = get_processors(environment)

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard Python logging (for external libraries).
    # This ensures uvicorn, sqlalchemy, httpx, etc. use the same format.
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Silence overly verbose libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
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
        return structlog.get_logger(name)
    return structlog.get_logger()
