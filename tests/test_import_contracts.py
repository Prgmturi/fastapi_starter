"""Tests for the import contracts in pyproject.toml ([tool.importlinter]).

WHY these tests exist: import-linter stops with an error when a layer or a
source module does not exist, but not when a forbidden module does not, nor
when a source pattern with * matches no module. A contract that names a
module after it moved stays kept and checks nothing (tried on 27 October
2026, before the Keycloak adapters moved to adapters/keycloak/).
"""

import pkgutil
import re
import tomllib
from pathlib import Path

import pytest

import fastapi_starter

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"
CONTRACTS = tomllib.loads(PYPROJECT.read_text())["tool"]["importlinter"]["contracts"]

# Every module and package of ours. walk_packages imports the packages, not
# the modules, to find what they hold.
MODULES = {"fastapi_starter"} | {
    module.name
    for module in pkgutil.walk_packages(fastapi_starter.__path__, "fastapi_starter.")
}


def our_names(contract: dict) -> list[str]:
    """Our module names in a contract: layers, containers, sources, forbidden."""
    names = [
        name.strip()
        for layer in contract.get("layers", [])
        for name in re.split(r"[|:]", layer)  # siblings, independent or not
    ]
    names += contract.get("containers", [])  # the packages that hold the layers
    names += contract.get("source_modules", []) + contract.get("forbidden_modules", [])
    # The others are packages such as httpx, there only to be forbidden
    return [name for name in names if name.split(".")[0] == "fastapi_starter"]


def matching_modules(name: str) -> list[str]:
    """Our modules a name stands for: * is one part of it, ** one or more."""
    pattern = (
        re.escape(name)
        .replace(re.escape("**"), r"[^.]+(?:\.[^.]+)*")
        .replace(re.escape("*"), r"[^.]+")
    )
    return [module for module in MODULES if re.fullmatch(pattern, module)]


NAMED = [
    (contract["name"], name) for contract in CONTRACTS for name in our_names(contract)
]


@pytest.mark.parametrize(
    ("contract", "name"),
    NAMED,
    ids=[f"{contract} / {name}" for contract, name in NAMED],
)
def test_every_named_module_exists(contract, name):
    """[EC] Each module a contract names exists, or each pattern matches one."""
    assert matching_modules(name), f'"{contract}" names {name}, which matches no module'


def test_patterns_are_read_as_import_linter_does():
    """[HP] * stands for one part of a name, ** for one or more.

    Memberships, not whole lists: adding a feature must not break the test.
    """
    one_part = matching_modules("fastapi_starter.features.*.router")
    assert "fastapi_starter.features.auth.router" in one_part
    assert "fastapi_starter.features.notes.api.router" not in one_part

    any_depth = matching_modules("fastapi_starter.**.router")
    assert "fastapi_starter.features.notes.api.router" in any_depth

    # The ports that "Ports import no adapter" covers, the feature's included
    assert {
        "fastapi_starter.core.auth.protocols",
        "fastapi_starter.core.database.protocols",
        "fastapi_starter.core.protocols",
        "fastapi_starter.features.notes.domain.protocols",
    } <= set(matching_modules("fastapi_starter.**.protocols"))
