from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_starter.core.database.base import Base

DEFAULT_PAGE_SIZE = 20
# A larger page is refused: one request must not read a whole table.
# Routers use it as the bound of their limit parameter, so clients get 422.
MAX_PAGE_SIZE = 100


class BaseRepository[ModelT: Base]:
    """
    Generic repository providing common CRUD operations.

    Subclass per entity:
        class UserRepository(BaseRepository[UserModel]):
            model = UserModel

    Transaction management is handled by the session dependency
    (commit on success, rollback on error). Repository methods use
    flush() to synchronize with the database within the transaction.
    """

    model: type[ModelT]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "model"):
            raise TypeError(f"{cls.__name__} must define a 'model' class attribute")

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: Any) -> ModelT | None:
        return await self._session.get(self.model, entity_id)

    async def get_page(
        self, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
    ) -> list[ModelT]:
        """One page of entities, in primary key order.

        Without ORDER BY, Postgres returns rows in the order it finds them,
        and an UPDATE moves a row: the next page skips one and repeats
        another. With the order, only a row deleted from an earlier page
        shifts the next ones by one, the known limit of offset paging.
        """
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
        if offset < 0:
            raise ValueError("offset must be 0 or more")

        statement = (
            select(self.model)
            .order_by(*inspect(self.model).primary_key)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def create(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)
        await self._session.flush()
