"""Tests for configure_logging — levels, processors and library records.

Module under test: src/fastapi_starter/core/logging/config.py
Layer: Infrastructure (structlog and stdlib logging setup)
"""

import copy
import json
import logging
import logging.config
from collections.abc import Iterator
from typing import Any

import pytest
import structlog
from uvicorn.config import LOGGING_CONFIG

from fastapi_starter.core.logging import configure_logging

# A handler writes to the stream it got when it was created, and capsys
# gives each phase of a test (setup, call, teardown) streams of its own,
# closed when the phase ends. So the tests create their handlers in their
# body: configure_logging, and dictConfig in uvicorn_logging().


@pytest.fixture(autouse=True)
def reset_logging() -> Iterator[None]:
    """Set logging up again at the end, as the app of any other test does.

    configure_logging changes the whole process, and a test here leaves it
    writing to the streams of capsys. Autouse fixtures start first and end
    last: this one ends after capsys, on the streams pytest keeps.
    """
    yield
    configure_logging()


def uvicorn_logging() -> None:
    """What uvicorn does to logging before it calls the app factory."""
    logging.config.dictConfig(copy.deepcopy(LOGGING_CONFIG))


def lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """stdout and stderr together, line by line, as `docker logs` shows them."""
    captured = capsys.readouterr()
    return (captured.out + captured.err).splitlines()


def only_json_line(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """The one line written, parsed. Fails if there are more, or none."""
    written = lines(capsys)
    assert len(written) == 1, written
    record: dict[str, Any] = json.loads(written[0])
    return record


class TestLogLevel:
    def test_unknown_level_refused(self):
        """[EC] A typo raises instead of becoming INFO.

        WHY: AppSettings refuses unknown levels, but configure_logging is
        also called directly. getattr(logging, "verbose", logging.INFO)
        hid the typo. The error comes before anything is configured.
        """
        with pytest.raises(ValueError, match="verbose"):
            configure_logging(log_level="verbose")


class TestAppRecords:
    def test_app_record_is_json_in_production(self, capsys):
        """[HP] structlog's own lines: JSON, with the service fields.

        WHY: the library records now share these processors; the app's
        lines must not change.
        """
        configure_logging(
            environment="production", app_name="fastapi-starter", version="1.2.3"
        )

        structlog.get_logger().info("user_created", user_id=7)

        record = only_json_line(capsys)
        assert record["event"] == "user_created"
        assert record["user_id"] == 7
        assert record["level"] == "info"
        assert record["service"] == "fastapi-starter"
        assert "logger" not in record


class TestLibraryRecords:
    """Records of the standard logging module: uvicorn, SQLAlchemy, httpx.

    WHY these tests exist: only structlog's lines were JSON. uvicorn gives
    its loggers their own handler and text format before it calls the app
    factory, and the root handler wrote the bare message of the others.
    """

    def test_uvicorn_record_is_json_in_production(self, capsys):
        """[HP] A uvicorn record is one JSON line, with the app's fields."""
        uvicorn_logging()
        configure_logging(
            environment="production", app_name="fastapi-starter", version="1.2.3"
        )

        logging.getLogger("uvicorn.error").info("Started server process [%d]", 42)

        record = only_json_line(capsys)
        assert record["event"] == "Started server process [42]"
        assert record["level"] == "info"
        assert record["logger"] == "uvicorn.error"
        assert record["service"] == "fastapi-starter"
        assert record["version"] == "1.2.3"
        assert "timestamp" in record

    @pytest.mark.parametrize("name", ["sqlalchemy.pool", "httpx"])
    def test_library_record_is_json_in_production(self, capsys, name):
        """[HP] SQLAlchemy and httpx records are JSON too, with their logger."""
        configure_logging(environment="production")

        logging.getLogger(name).warning("Pool pre-ping failed, reconnecting")

        record = only_json_line(capsys)
        assert record["event"] == "Pool pre-ping failed, reconnecting"
        assert record["level"] == "warning"
        assert record["logger"] == name

    def test_traceback_stays_in_its_line(self, capsys):
        """[HP] An exception is one JSON line, the traceback in "exception".

        WHY: as text, every line of a traceback reached `docker logs` as an
        event of its own.
        """
        uvicorn_logging()
        configure_logging(environment="production")

        try:
            raise RuntimeError("bug in a route")
        except RuntimeError:
            logging.getLogger("uvicorn.error").exception(
                "Exception in ASGI application"
            )

        record = only_json_line(capsys)
        assert record["level"] == "error"
        assert "RuntimeError: bug in a route" in record["exception"]

    def test_access_line_is_off(self, capsys):
        """[SEC] uvicorn's access line is not written.

        WHY: request_completed says the same, with the request id and the
        duration, and the access line carried the query string, which can
        hold personal data.
        """
        uvicorn_logging()
        configure_logging(environment="production")

        logging.getLogger("uvicorn.access").info(
            '%s - "%s %s HTTP/%s" %d',
            "203.0.113.7:50000",
            "GET",
            "/health/live?email=mario.rossi@example.com",
            "1.1",
            200,
        )

        assert lines(capsys) == []

    def test_log_level_applies_to_uvicorn(self, capsys):
        """[EC] With APP_LOG_LEVEL=WARNING uvicorn's INFO lines are not written.

        WHY: uvicorn's own handler ignored the level of the app.
        """
        uvicorn_logging()
        configure_logging(environment="production", log_level="WARNING")

        logging.getLogger("uvicorn.error").info("Waiting for application startup.")

        assert lines(capsys) == []

    def test_development_uses_the_console_format(self, capsys):
        """[HP] In development uvicorn's lines look like the app's lines.

        WHY: one format in development too: the app's columns and the name
        of the logger, instead of uvicorn's "INFO:     " prefix.
        """
        uvicorn_logging()
        configure_logging(environment="development")

        logging.getLogger("uvicorn.error").info("Application startup complete.")

        [line] = lines(capsys)
        assert "Application startup complete." in line
        assert "uvicorn.error" in line
        assert not line.startswith("INFO:")
