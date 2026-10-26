"""End-to-end fixtures: the stack of compose.yaml, running.

Every test in this folder gets the ``e2e`` marker. A plain ``pytest``
leaves them out (addopts in pyproject.toml); ``pytest -m e2e`` runs only
them, against the API at E2E_API_URL (http://localhost:8000 by default)
after ``docker compose up --build --wait``.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).parent


# tryfirst: the marker must be there before pytest deselects by -m.
# The hook sees the items of the whole run, hence the path check.
@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(HERE):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture
def api() -> Iterator[httpx.Client]:
    """A client of the running API."""
    base_url = os.environ.get("E2E_API_URL", "http://localhost:8000")
    with httpx.Client(base_url=base_url, timeout=10) as client:
        yield client
