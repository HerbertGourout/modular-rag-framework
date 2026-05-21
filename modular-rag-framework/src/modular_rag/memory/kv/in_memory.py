"""In-memory key-value store implementing the Storage contract."""
from __future__ import annotations


class InMemoryStorage:
    """Simple dict-backed storage for development and testing."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def name(self) -> str:
        return "in-memory"

    def put(self, key: str, value: bytes) -> None:
        self._store[key] = value

    def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._store
