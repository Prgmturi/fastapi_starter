"""Tests for the runtime dependencies declared in pyproject.toml.

WHY these tests exist: python-keycloak stayed a dependency after the code
stopped importing it, and pulled jwcrypto into every install and image.
The extra pydantic[email] outlived the last EmailStr the same way. A
dependency the code does not import must say why it is there.
"""

import ast
import importlib.metadata
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Dependencies the code uses without importing them
USED_WITHOUT_IMPORT = {
    "asyncpg": "SQLAlchemy imports it for the postgresql+asyncpg URL",
}

# Extras: what each one adds, and why the app needs it
EXTRAS_WITH_A_REASON = {
    "pyjwt[crypto]": "cryptography, for the RS256 signatures of Keycloak tokens",
    "uvicorn[standard]": "uvloop and httptools, which uvicorn picks up by itself",
}


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared() -> list[tuple[str, list[str]]]:
    """(distribution, extras) for each entry of [project].dependencies."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    result = []
    for spec in pyproject["project"]["dependencies"]:
        match = re.match(r"([A-Za-z0-9_.-]+)(?:\[([^\]]*)\])?", spec)
        assert match is not None, spec
        extras = [e.strip() for e in (match.group(2) or "").split(",") if e.strip()]
        result.append((normalized(match.group(1)), extras))
    return result


def imported_modules() -> set[str]:
    """Top-level modules imported anywhere in src/ and alembic/."""
    modules = set()
    for path in [*ROOT.glob("src/**/*.py"), *ROOT.glob("alembic/**/*.py")]:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                modules.add(node.module.split(".")[0])
    return modules


def modules_of(distribution: str) -> set[str]:
    return {
        module
        for module, dists in importlib.metadata.packages_distributions().items()
        if distribution in {normalized(d) for d in dists}
    }


class TestRuntimeDependencies:
    def test_every_dependency_is_imported_or_explained(self):
        """[HP] No dependency the code neither imports nor needs."""
        imported = imported_modules()
        unused = [
            name
            for name, _ in declared()
            if not modules_of(name) & imported and name not in USED_WITHOUT_IMPORT
        ]

        assert unused == []

    def test_every_extra_is_explained(self):
        """[HP] An extra installs packages nobody imports: it needs a reason."""
        unexplained = [
            f"{name}[{extra}]"
            for name, extras in declared()
            for extra in extras
            if f"{name}[{extra}]" not in EXTRAS_WITH_A_REASON
        ]

        assert unexplained == []
