from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from fastapi_starter.core.config.database import DatabaseSettings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class DatabaseManager:
    """
    Manages database connections and sessions.

    Usage:
        manager = DatabaseManager(settings.database)
        await manager.connect()
        await manager.health_check()

        # Use sessions via dependency injection

        await manager.disconnect()
    """

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Get the database engine. Creates it if not exists."""
        if self._engine is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory. Requires engine to be created."""
        if self._session_factory is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._session_factory

    async def connect(self) -> None:
        """
        Initialize the database connection.

        Creates the engine and session factory.
        Should be called once at application startup.
        """
        if self._engine is not None:
            return  # Already connected

        self._engine = create_async_engine(
            self._settings.url,
            pool_size=self._settings.pool_size,
            max_overflow=self._settings.pool_max_overflow,
            pool_timeout=self._settings.pool_timeout,
            pool_recycle=self._settings.pool_recycle,
            echo=self._settings.echo,
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def disconnect(self) -> None:
        """
        Close the database connection.

        Disposes the engine and clears references.
        Should be called once at application shutdown.
        """
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def get_session(self) -> AsyncSession:
        """
        Get a new database session.

        Note: Prefer using the dependency injection via DbSession.
        """
        return self.session_factory()

    async def health_check(self) -> bool:
        """
        Check if database is reachable.

        Returns:
            True if database responds to a simple query.

        Raises:
            RuntimeError: If not connected.
            SQLAlchemyError: If database is unreachable.
        """
        async with self.session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
