from __future__ import annotations

import uuid


def new_id() -> str:
    """Return a new random UUID4 string."""
    return str(uuid.uuid4())


def short_id() -> str:
    """Return the first 8 chars of a UUID4 — for human-readable labels."""
    return str(uuid.uuid4())[:8]
