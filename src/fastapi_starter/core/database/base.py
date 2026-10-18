from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models.

    Alembic reads Base.metadata to autogenerate migrations, so every model
    must be imported in alembic/env.py.
    """
