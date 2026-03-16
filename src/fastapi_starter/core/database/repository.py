from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_starter.core.database.manager import Base


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

    async def get_all(self) -> list[ModelT]:
        result = await self._session.execute(select(self.model))
        return list(result.scalars().all())

    async def create(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)
        await self._session.flush()
