"""Stable document identity and content hashing helpers."""

import hashlib


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def document_key(source: str, tenant_id: str | None = None) -> str:
    raw = f"{tenant_id or 'default'}:{source}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
