from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_starter.core.database.protocols import DatabaseProvider


def get_db_manager(request: Request) -> DatabaseProvider:
    """
    Get database provider from app state.

    The manager is stored in app.state during startup.
    """
    try:
        manager: DatabaseProvider = request.app.state.db_manager
        return manager
    except AttributeError as err:
        raise RuntimeError("DatabaseManager not initialized") from err


async def get_db_session(
    db_manager: Annotated[DatabaseProvider, Depends(get_db_manager)],
) -> AsyncGenerator[AsyncSession]:
    """
    Dependency that provides a database session.

    The session is automatically closed after the request.
    Commits on success, rolls back on exception.

    Use it through ``DbSession``, which ends it before the response is sent.
    """
    async with db_manager.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# scope="function": the commit runs when the endpoint returns, before the
# response is sent, so a failed commit becomes a 500. With FastAPI's default
# scope ("request") it would run after the response has left, and the client
# would get 201 for data that was never saved.
# The session is closed by then: background tasks and streaming responses
# must open their own.
DbSession = Annotated[AsyncSession, Depends(get_db_session, scope="function")]
