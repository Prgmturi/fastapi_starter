"""Tests for core/state.py — StateKey, and the one way into app.state.

Module under test: src/fastapi_starter/core/state.py
Layer: Core, no I/O

WHY these tests exist: app.state has no types. bootstrap.py stored each
adapter through a variable typed as its port, so that mypy compared the
two; an adapter stored without one passed mypy and every test, and a
route failed at runtime with a TypeError (tried on 2 November 2026, with
a port changed and its adapter not).
"""

import ast
from pathlib import Path

import pytest
from starlette.datastructures import State

import fastapi_starter
from fastapi_starter.core.state import StateKey

SRC = Path(fastapi_starter.__file__).parent

# The one write by hand: the settings are no adapter, and have no port
ALLOWED = {("main.py", "settings")}


def is_state(node: ast.expr) -> bool:
    """app.state, request.app.state, or a variable called state or app_state."""
    if isinstance(node, ast.Attribute):
        return node.attr == "state"
    return isinstance(node, ast.Name) and node.id in {"state", "app_state"}


def state_writes(source: str) -> list[str]:
    """The names a module writes in app.state by hand, setattr() included."""
    writes = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        else:
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "setattr"
                and is_state(node.args[0])
            ):
                writes.append("setattr")
            continue
        writes += [
            target.attr
            for target in targets
            if isinstance(target, ast.Attribute) and is_state(target.value)
        ]
    return writes


class TestStateKey:
    def test_get_returns_what_set_stored(self):
        """[HP] set() then get() -> the same object."""
        key = StateKey[object]("service")
        state = State()
        service = object()

        key.set(state, service)

        assert key.get(state) is service

    def test_stores_under_its_name(self):
        """[HP] The value is the attribute of that name.

        WHY: tests replace a service by its name, app.state.db_manager.
        """
        state = State()

        StateKey[int]("answer").set(state, 42)

        assert state.answer == 42

    def test_get_before_set_raises(self):
        """[EC] Nothing stored -> AttributeError, as app.state raises.

        WHY: get_db_manager turns it into "DatabaseManager not initialized".
        """
        with pytest.raises(AttributeError):
            StateKey[int]("missing").get(State())


class TestOneWayIntoAppState:
    def test_src_writes_app_state_only_through_a_key(self):
        """[EC] No module of src/ sets an attribute of app.state by hand.

        WHY: a write by hand has no type, so mypy cannot compare the
        adapter with its port. StateKey.set() is the one way in.
        """
        found = [
            f"{path.relative_to(SRC)}: {name}"
            for path in sorted(SRC.rglob("*.py"))
            if path != SRC / "core" / "state.py"
            for name in state_writes(path.read_text())
            if (str(path.relative_to(SRC)), name) not in ALLOWED
        ]

        assert not found, f"Store these through a StateKey (core/state.py): {found}"

    def test_the_check_sees_every_kind_of_write(self):
        """[HP] The four ways to write app.state are found, reads are not.

        WHY: a check that finds nothing passes on any code.
        """
        source = "\n".join(
            [
                "app.state.db_manager = manager",
                "request.app.state.provider: OAuthProvider = client",
                "app_state.count += 1",
                "setattr(state, 'auth_service', service)",
                "service = request.app.state.auth_service",
                "other.thing = 1",
            ]
        )

        assert state_writes(source) == [
            "db_manager",
            "provider",
            "count",
            "setattr",
        ]

    def test_the_one_write_allowed_is_found(self):
        """[HP] main.py stores the settings by hand, and the check sees it."""
        assert state_writes((SRC / "main.py").read_text()) == ["settings"]
