from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Names for indexes and constraints. Without them Postgres picks its own,
# Alembic cannot know them, and the downgrade it generates
# (drop_constraint(None, ...)) does not run. column_0_N_name joins every
# column, so two constraints that start with the same column still get two
# names. A CHECK needs a name of its own, CheckConstraint(..., name="..."):
# the convention adds the table in front.
# Changing these after the first migration renames existing constraints.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models.

    Alembic reads Base.metadata to autogenerate migrations, so every model
    must be imported in alembic/env.py.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
