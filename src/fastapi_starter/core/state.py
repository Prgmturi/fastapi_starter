"""Typed names for the services in app.state.

app.state takes any attribute, and has no types: what is stored there is
Any wherever it is read or written. A StateKey gives a name one type, the
port. bootstrap.py stores an adapter with key.set(), so mypy checks that
the adapter matches the port; a dependency reads it with key.get(), and
gets the port. aiohttp does the same with web.AppKey.

tests/core/test_state.py refuses any other write to app.state in src/.
"""

from starlette.datastructures import State


class StateKey[T]:
    """A name in app.state, and the type of what it holds."""

    def __init__(self, name: str) -> None:
        self.name = name

    def set(self, state: State, value: T) -> None:
        setattr(state, self.name, value)

    def get(self, state: State) -> T:
        """What set() stored under the name.

        Raises:
            AttributeError: If nothing was stored, as app.state does.
        """
        value: T = getattr(state, self.name)
        return value
