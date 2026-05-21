from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    """Key-value byte store for serialised objects (traces, graphs, manifests)."""

    def put(self, key: str, value: bytes) -> None: ...

    def get(self, key: str) -> bytes | None: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def name(self) -> str: ...
