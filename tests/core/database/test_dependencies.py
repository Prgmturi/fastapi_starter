"""Tests for database dependencies — session lifecycle.

Module under test: src/fastapi_starter/core/database/dependencies.py
Layer: FastAPI integration

WHY these tests exist: get_db_session is a critical dependency that handles
commit/rollback. If this breaks, every database operation either silently
loses data (no commit) or leaves zombie transactions (no rollback).
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastapi_starter.core.database.dependencies import get_db_manager, get_db_session


class TestGetDbManager:
    """get_db_manager — retrieves DatabaseProvider from app.state.

    WHY: Bridge between FastAPI request and database layer.
    """

    def test_returns_manager_from_app_state(self):
        """[HP] Returns request.app.state.db_manager."""
        mock_manager = AsyncMock()
        mock_request = MagicMock()
        mock_request.app.state.db_manager = mock_manager

        result = get_db_manager(mock_request)

        assert result is mock_manager

    def test_raises_runtime_error_when_not_initialized(self):
        """[EC] Missing db_manager in state -> RuntimeError.

        WHY: Fail fast with a clear message instead of AttributeError.
        """
        mock_request = MagicMock()
        del mock_request.app.state.db_manager

        with pytest.raises(RuntimeError, match="not initialized"):
            get_db_manager(mock_request)


class TestGetDbSession:
    """get_db_session — session lifecycle (commit/rollback).

    WHY: This dependency guarantees transactional integrity:
    1. Success -> commit
    2. Exception -> rollback then re-raise
    If either behavior breaks, data corruption or data loss occurs.
    """

    async def test_commits_on_success(self):
        """[HP] Normal flow -> session.commit() called."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_manager = MagicMock()
        mock_manager.session_factory.return_value = mock_session

        gen = get_db_session(mock_manager)
        session = await gen.__anext__()

        assert session is mock_session

        # Simulate request completing successfully
        with contextlib.suppress(StopAsyncIteration):
            await gen.__anext__()

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    async def test_rolls_back_on_exception(self):
        """[EC] Exception during request -> session.rollback() called."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_manager = MagicMock()
        mock_manager.session_factory.return_value = mock_session

        gen = get_db_session(mock_manager)
        await gen.__anext__()

        # Simulate exception during request
        with pytest.raises(ValueError, match="something broke"):
            await gen.athrow(ValueError("something broke"))

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    async def test_re_raises_exception_after_rollback(self):
        """[EC] After rollback, the original exception propagates.

        WHY: The session dependency must not swallow exceptions.
        """
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_manager = MagicMock()
        mock_manager.session_factory.return_value = mock_session

        gen = get_db_session(mock_manager)
        await gen.__anext__()

        with pytest.raises(RuntimeError, match="original error"):
            await gen.athrow(RuntimeError("original error"))
