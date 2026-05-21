# ADR-0002 — Contracts as Python Protocols + Factory Registry

**Status:** Accepted  
**Date:** 2026-05-20  
**Authors:** Herbert Gourout, Publicis Data Specialists

---

## Context

We need a mechanism to:
1. Define clear interfaces that any third-party or internal implementation must satisfy.
2. Allow swapping implementations at runtime via YAML manifests, without changing Python code.
3. Keep the framework usable as a library (no mandatory base classes for users).

Two options were considered:
- **ABC (Abstract Base Classes)**: enforce inheritance; implementations must subclass.
- **typing.Protocol**: structural subtyping; any class with the right methods satisfies the protocol — no inheritance required.

---

## Decision

All contracts use `typing.Protocol` with `@runtime_checkable`.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Chunker(Protocol):
    def chunk(self, document: Document) -> list[Chunk]: ...
    def name(self) -> str: ...
```

Implementations are registered in `ComponentRegistry` via factory callables:

```python
registry.register("chunker", "adaptive", lambda cfg: AdaptiveChunker(**cfg.config))
```

The manifest selects the implementation by type name:
```yaml
chunker:
  type: adaptive
  config:
    chunk_size: 512
```

This fully decouples component selection from Python code.

---

## Consequences

**Positive**
- Third-party implementations do not need to import the framework.
- `isinstance(obj, Chunker)` works at runtime for contract tests.
- Config is entirely in YAML — no Python needed to swap components.

**Negative**
- Protocol structural checking is not as strict as ABC at import time (only at `isinstance` check).
- The registry must be explicitly populated; forgetting a registration causes a `RegistryError` at pipeline load time, not at import time.

**Boundary: `core/models/` vs `contracts/`**

`core/models/` contains **data** (Pydantic models: Document, Chunk, Query, etc.). Contracts reference these models but never define data themselves. This prevents circular imports: contracts → models, never models → contracts.
