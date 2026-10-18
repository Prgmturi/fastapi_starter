"""Tests for configure_logging — levels and processors.

Module under test: src/fastapi_starter/core/logging/config.py
Layer: Infrastructure (structlog and stdlib logging setup)
"""

import pytest

from fastapi_starter.core.logging import configure_logging


class TestLogLevel:
    def test_unknown_level_refused(self):
        """[EC] A typo raises instead of becoming INFO.

        WHY: AppSettings refuses unknown levels, but configure_logging is
        also called directly. getattr(logging, "verbose", logging.INFO)
        hid the typo. The error comes before anything is configured.
        """
        with pytest.raises(ValueError, match="verbose"):
            configure_logging(log_level="verbose")
