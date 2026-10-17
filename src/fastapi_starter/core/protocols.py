"""Cross-cutting protocols shared across core modules."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HealthCheckable(Protocol):
    """Reports whether a component can do its job right now.

    health_check returns False or raises when it cannot. The readiness
    probe calls it every few seconds, so it must be cheap.
    """

    async def health_check(self) -> bool: ...


@runtime_checkable
class KeyProvider(Protocol):
    """Provides cryptographic signing keys for token verification."""

    async def get_signing_key_from_token(self, token: str) -> Any: ...

    async def health_check(self) -> bool: ...
