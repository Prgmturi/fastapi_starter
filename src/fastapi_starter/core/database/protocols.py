"""Database-specific protocols."""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DatabaseProvider(Protocol):
    """Provides database sessions and health checking."""

    async def health_check(self) -> bool: ...

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]: ...
