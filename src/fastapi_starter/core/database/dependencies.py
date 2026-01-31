from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_starter.core.database.manager import DatabaseManager


def get_db_manager(request: Request) -> DatabaseManager:
    """
    Get DatabaseManager from app state.

    The manager is stored in app.state during startup.
    """
    try:
        return request.app.state.db_manager
    except AttributeError as err:
        raise RuntimeError("DatabaseManager not initialized") from err


async def get_db_session(
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> AsyncGenerator[AsyncSession]:
    """
    Dependency that provides a database session.

    The session is automatically closed after the request.
    Commits on success, rolls back on exception.
    """
    async with db_manager.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
