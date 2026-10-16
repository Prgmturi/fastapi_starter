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
from sqlalchemy.exc import SQLAlchemyError

from fastapi_starter.core.database.dependencies import (
    DbSession,
    get_db_manager,
    get_db_session,
)


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


class TestDbSessionInRequest:
    """DbSession inside a real request — the commit decides the response.

    WHY: by default FastAPI runs the code after ``yield`` once the response
    has been sent. A commit that failed there could not change the status
    code: the client would get 201 for data that was never saved.
    """

    @pytest.fixture
    def session(self, mock_db_provider, mock_session):
        """mock_session, handed out by the app's database provider."""
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_db_provider.session_factory = MagicMock(return_value=mock_session)
        return mock_session

    @pytest.fixture
    def orders_app(self, app):
        """The test app plus a route that writes through DbSession."""

        @app.post("/orders", status_code=201)
        async def create_order(session: DbSession) -> dict[str, int]:
            return {"id": 42}

        return app

    async def test_successful_commit_returns_201(self, orders_app, client, session):
        """[HP] Commit succeeds -> 201, one commit, no rollback."""
        response = await client.post("/orders")

        assert response.status_code == 201
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    async def test_failed_commit_returns_500(self, orders_app, client, session):
        """[EC] Commit fails -> 500 and rollback, never 201.

        WHY: a 201 tells the client the data exists. After a failed commit
        it does not.
        """
        session.commit.side_effect = SQLAlchemyError("commit failed")

        response = await client.post("/orders")

        assert response.status_code == 500
        session.rollback.assert_awaited_once()
