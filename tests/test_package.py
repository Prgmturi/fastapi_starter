"""Tests for the package itself — what importing it loads.

Module under test: src/fastapi_starter/__init__.py
Layer: Package structure

WHY these tests exist: Python runs a package's __init__.py before any of
its modules. When it imported the routers, every tool that needed a
single module of core loaded the auth and health features too: Alembic
at each migration, a script that reads the settings, a test.
"""

import subprocess
import sys
import textwrap

# Imports every module of core, then lists the modules of features and
# adapters it loaded.
IMPORT_ALL_OF_CORE = textwrap.dedent(
    """
    import pkgutil
    import sys

    import fastapi_starter.core as core

    for module in pkgutil.walk_packages(core.__path__, "fastapi_starter.core."):
        __import__(module.name)

    loaded = sorted(sys.modules)
    print([
        name
        for name in loaded
        if name.startswith(("fastapi_starter.features", "fastapi_starter.adapters"))
    ])
    """
)


class TestImportCore:
    def test_core_loads_no_feature_and_no_adapter(self, tmp_path):
        """[EC] Importing any module of core loads no feature and no adapter.

        WHY: core must not depend on features nor on adapters. import-linter reads the
        import statements of each module, but not what a package's
        __init__.py pulls in. In a subprocess, because in this one
        conftest.py has already imported the whole app.
        """
        result = subprocess.run(
            [sys.executable, "-c", IMPORT_ALL_OF_CORE],
            cwd=tmp_path,  # no .env in this directory
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "[]"
