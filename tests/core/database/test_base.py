"""Tests for Base — the names of indexes and constraints.

Module under test: src/fastapi_starter/core/database/base.py
Layer: Infrastructure (SQLAlchemy metadata, Alembic autogenerate)

WHY these tests exist: without a naming convention Postgres names each
constraint itself and Alembic cannot know that name. A migration that adds
a unique constraint then gets op.drop_constraint(None, ...) as its
downgrade, and that downgrade does not run.
"""

import io
from collections.abc import Iterator

import pytest
from alembic.autogenerate import produce_migrations
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.operations.ops import MigrateOperation
from sqlalchemy import (
    CheckConstraint,
    Column,
    Connection,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.schema import CreateTable

from fastapi_starter.core.database.base import Base

TABLES = ("convention_customers", "convention_orders")

# The schema an earlier migration left, with the convention's names: the
# same tables, email not yet unique. NOT NULL because SQLite reads a bare
# INTEGER PRIMARY KEY as nullable.
EARLIER_SCHEMA = [
    "CREATE TABLE convention_customers (id INTEGER NOT NULL PRIMARY KEY)",
    "CREATE TABLE convention_orders ("
    " id INTEGER NOT NULL PRIMARY KEY, email VARCHAR(320), tenant VARCHAR(50),"
    " code VARCHAR(50), sku VARCHAR(50),"
    " customer_id INTEGER REFERENCES convention_customers (id),"
    " CONSTRAINT uq_convention_orders_tenant_email UNIQUE (tenant, email),"
    " CONSTRAINT uq_convention_orders_tenant_code UNIQUE (tenant, code),"
    " CHECK (id > 0))",
    "CREATE INDEX ix_convention_orders_sku ON convention_orders (sku)",
    "CREATE INDEX ix_convention_orders_tenant_sku ON convention_orders (tenant, sku)",
]


@pytest.fixture
def orders() -> Iterator[Table]:
    """convention_orders and the table it refers to, on the real Base.metadata.

    Removed after the test: Alembic reads Base.metadata, and other tests
    must not find these tables there.
    """
    customers = Table(
        "convention_customers",
        Base.metadata,
        Column("id", Integer, primary_key=True),
    )
    orders = Table(
        "convention_orders",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("email", String(320), unique=True),
        Column("tenant", String(50)),
        Column("code", String(50)),
        Column("sku", String(50), index=True),
        Column("customer_id", ForeignKey("convention_customers.id")),
        # Two unique constraints that start with the same column
        UniqueConstraint("tenant", "email"),
        UniqueConstraint("tenant", "code"),
        Index(None, "tenant", "sku"),
        CheckConstraint("id > 0", name="id_positive"),
    )
    yield orders
    Base.metadata.remove(orders)
    Base.metadata.remove(customers)


@pytest.fixture
def earlier_database() -> Iterator[Connection]:
    """An in-memory SQLite database holding EARLIER_SCHEMA."""
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for statement in EARLIER_SCHEMA:
            connection.exec_driver_sql(statement)
        yield connection
    engine.dispose()


def flatten(operations: list[MigrateOperation]) -> Iterator[MigrateOperation]:
    """The single operations inside Alembic's per-table groups."""
    for operation in operations:
        if hasattr(operation, "ops"):
            yield from flatten(operation.ops)
        else:
            yield operation


def as_postgres_sql(operations: list[MigrateOperation]) -> str:
    """The SQL these operations produce on Postgres, without a database."""
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    for operation in flatten(operations):
        Operations(context).invoke(operation)
    return output.getvalue()


class TestNamingConvention:
    """Base.metadata names every index and constraint the same way."""

    def test_every_constraint_gets_a_predictable_name(self, orders):
        """[HP] Names built from table and columns, the same in every database."""
        ddl = str(CreateTable(orders).compile(dialect=postgresql.dialect()))

        for name in (
            "pk_convention_orders",
            "uq_convention_orders_email",
            # Every column in the name: two constraints, two names
            "uq_convention_orders_tenant_email",
            "uq_convention_orders_tenant_code",
            "fk_convention_orders_customer_id_convention_customers",
            "ck_convention_orders_id_positive",
        ):
            assert f"CONSTRAINT {name} " in ddl
        assert {index.name for index in orders.indexes} == {
            "ix_convention_orders_sku",
            "ix_convention_orders_tenant_sku",
        }

    def test_generated_downgrade_drops_the_constraint_by_name(
        self, orders, earlier_database
    ):
        """[EC] email made unique later -> Alembic writes a downgrade that runs.

        WHY: without a name the downgrade is drop_constraint(None, ...), and
        Alembic refuses to turn it into SQL.
        """
        context = MigrationContext.configure(
            earlier_database,
            opts={
                # Only these tables: Base.metadata may hold others, like
                # FakeModel from tests/core/database/fakes.py
                "include_object": lambda obj, name, type_, reflected, other: (
                    type_ != "table" or name in TABLES
                ),
            },
        )
        script = produce_migrations(context, Base.metadata)

        upgrade = as_postgres_sql(script.upgrade_ops.ops)
        downgrade = as_postgres_sql(script.downgrade_ops.ops)

        assert "ADD CONSTRAINT uq_convention_orders_email UNIQUE (email)" in upgrade
        assert "DROP CONSTRAINT uq_convention_orders_email" in downgrade
        # ...and it is the only difference Alembic finds
        changes = [type(change).__name__ for change in flatten(script.upgrade_ops.ops)]
        assert changes == ["CreateUniqueConstraintOp"]

    def test_check_constraint_needs_its_own_name(self):
        """[EC] An unnamed CHECK -> an error where the table is defined.

        WHY: the convention builds the CHECK name from the name you give it
        (ck_<table>_<name>), so the model must give one. The error comes at
        import, not when a migration runs.
        """
        with pytest.raises(InvalidRequestError, match="explicitly named"):
            Table(
                "convention_unnamed_check",
                Base.metadata,
                Column("id", Integer, primary_key=True),
                CheckConstraint("id > 0"),
            )

        assert "convention_unnamed_check" not in Base.metadata.tables
