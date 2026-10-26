"""Tests for the smoke test of the image, in the docker job of ci.yml.

WHY these tests exist: the step builds the app inside the image CI has
just built, with no database or Keycloak, and it counted the routes with
len(app.routes). Since FastAPI 0.137 app.routes keeps each included
router as one entry: the log said "12 routes registered" before FastAPI
0.161 and "7" after, for the same app (PR #54, 26 October 2026). Its
check, assert app.routes, passed with any route left.

The tests run the step's own code, read from ci.yml, in this process.
"""

import re
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from starlette.routing import NoMatchFound

from fastapi_starter import main

CI_WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


def smoke_test() -> str:
    """The Python code the step runs in the image: python -c "<code>"."""
    steps = yaml.safe_load(CI_WORKFLOW.read_text())["jobs"]["docker"]["steps"]
    run = next(step["run"] for step in steps if step.get("name") == "Smoke test")
    code = re.search(r'python -c \\\s*"(.+)"', run, re.S)
    assert code, run
    return code.group(1)


class TestSmokeTest:
    def test_finds_a_route_of_each_router(self, capsys):
        """[HP] The app builds, and the step prints a path from each router."""
        exec(smoke_test(), {})

        assert capsys.readouterr().out == "routes found: / /health/live /auth/me\n"

    def test_fails_without_the_routes_of_the_app(self, monkeypatch):
        """[EC] An app without our routes fails the step.

        WHY: an empty FastAPI() has routes too, its documentation pages, so
        a check that only asks for some routes passes.
        """
        monkeypatch.setattr(main, "create_app", FastAPI)

        with pytest.raises(NoMatchFound):
            exec(smoke_test(), {})
