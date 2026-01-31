"""Cross-cutting protocols shared across core modules."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HealthCheckable(Protocol):
    """Supports connectivity health checking."""

    async def health_check(self) -> bool: ...


@runtime_checkable
class KeyProvider(Protocol):
    """Provides cryptographic signing keys for token verification."""

    async def get_signing_key_from_token(self, token: str) -> Any: ...

    async def health_check(self) -> bool: ...
