"""What alembic/env.py needs: every model in Base.metadata, and a guard.

A model registers its table in Base.metadata when its module is imported,
and Alembic compares Base.metadata with the database. A model whose module
nobody imports is missing from every migration, without an error.
"""

import importlib
import pkgutil
from types import ModuleType

from sqlalchemy import MetaData

# Models live in modules with this name, at any depth: features/x/models.py,
# features/x/persistence/models.py
MODELS_MODULE = "models"


def import_models(package: ModuleType) -> list[str]:
    """Import every module called models under package.

    Returns:
        The names of the modules imported, in alphabetical order.
    """
    found = sorted(
        module.name
        for module in pkgutil.walk_packages(package.__path__, f"{package.__name__}.")
        if module.name.rsplit(".", 1)[-1] == MODELS_MODULE
    )
    for name in found:
        importlib.import_module(name)
    return found


def refuse_empty_autogenerate(metadata: MetaData) -> None:
    """Stop an autogenerate that would drop every table.

    With no table in the metadata, autogenerate compares nothing with the
    database and writes a drop_table for each of its tables: a plausible
    migration that deletes production. alembic/env.py calls this before it
    connects, and only for --autogenerate: upgrade and downgrade must work
    with no model, or no hand-written migration could run.

    Raises:
        RuntimeError: If the metadata has no table.
    """
    if not metadata.tables:
        raise RuntimeError(
            "autogenerate stopped: Base.metadata has no table, so Alembic would "
            "write a drop_table for every table of the database. Put the models "
            "in a module called models under fastapi_starter/features, where "
            "alembic/env.py finds them."
        )
