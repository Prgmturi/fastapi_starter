"""Tests for database dependencies — session lifecycle.

Module under test: src/fastapi_starter/core/database/dependencies.py
Layer: FastAPI integration

WHY these tests exist: get_db_session is a critical dependency that handles
commit/rollback. If this breaks, every database operation either silently
loses data (no commit) or leaves zombie transactions (no rollback).
"""

import pytest


class TestGetDbManager:
    """get_db_manager — retrieves DatabaseProvider from app.state.

    WHY: Bridge between FastAPI request and database layer.
    """

    def test_returns_manager_from_app_state(self):
        """[HP] Returns request.app.state.db_manager."""
        pytest.skip("Not implemented yet")

    def test_raises_runtime_error_when_not_initialized(self):
        """[EC] Missing db_manager in state -> RuntimeError.

        WHY: Fail fast with a clear message instead of AttributeError.
        """
        pytest.skip("Not implemented yet")


class TestGetDbSession:
    """get_db_session — session lifecycle (commit/rollback).

    WHY: This dependency guarantees transactional integrity:
    1. Success -> commit
    2. Exception -> rollback then re-raise
    If either behavior breaks, data corruption or data loss occurs.
    """

    async def test_commits_on_success(self):
        """[HP] Normal flow -> session.commit() called."""
        pytest.skip("Not implemented yet")

    async def test_rolls_back_on_exception(self):
        """[EC] Exception during request -> session.rollback() called."""
        pytest.skip("Not implemented yet")

    async def test_re_raises_exception_after_rollback(self):
        """[EC] After rollback, the original exception propagates.

        WHY: The session dependency must not swallow exceptions.
        """
        pytest.skip("Not implemented yet")
