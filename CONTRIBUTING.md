# Contributing

This document exists because the framework's value depends entirely on its architectural
discipline holding up as more people touch it: the hexagonal layering, the contract-first
approach, and the manifest-driven wiring only stay useful if every contribution respects
them. A single cross-domain import or a component wired directly in Python instead of
through a manifest quietly erodes the guarantees the rest of the codebase relies on — which
is why the rules below are enforced rather than just suggested.

## Before you start

0. New to this project? Read [docs/onboarding.md](docs/onboarding.md) first — it explains
   which of the documents below matter for your role (developer, tech lead, delivery
   consultant, functional/business profile, security) and in what order.
1. Read [CLAUDE.md](CLAUDE.md) — it documents the architectural rules you must follow.
2. Read [docs/architecture/overview.md](docs/architecture/overview.md) — the technical specification.
3. Read the relevant ADR(s) in [docs/adr/](docs/adr/) for the area you are modifying.
4. If you use Claude Code, read [docs/guides/claude-code.md](docs/guides/claude-code.md).
5. If you use multiple AI providers, read [docs/guides/ai-engineering-workflow.md](docs/guides/ai-engineering-workflow.md)
   and [docs/guides/model-routing.md](docs/guides/model-routing.md).

## Development setup

```bash
git clone https://pscode.lioncloud.net/data_specialiste/advancedpublicisrag.git
cd advancedpublicisrag/modular-rag-framework
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e .[v1,dev]
```

## Code rules

Each rule below exists to prevent a specific, previously-identified failure mode — not as
style preference. See [docs/architecture/module-model.md](docs/architecture/module-model.md)
for the worked examples of what breaks when a rule is skipped.

- **Contracts first**: add or update the Protocol in `contracts/` before writing an
  implementation. This keeps the interface the thing everyone agrees on before any one
  implementation biases the design.
- **No cross-domain imports**: `ingestion/` must not import from `generation/`. Both
  communicate through `contracts/` and `core/models/`. Skipping this means a unit test for a
  chunker could start silently requiring an LLM API key, because generation code got pulled
  in transitively.
- **Register in `_default_factories.py`**: every new built-in adapter must be registered by
  type name. A component that exists in code but isn't registered is invisible to every
  manifest — it simply cannot be selected, which is by design: nothing runs unless a
  manifest says so.
- **Tests mirror `src/`**: `tests/unit/ingestion/chunkers/test_fixed.py` mirrors
  `src/modular_rag/ingestion/chunkers/fixed.py`. This mapping is what lets anyone find the
  test for a given file without searching — it does not scale if tests are grouped any other
  way once there are hundreds of components.
- **Contract tests** go in `tests/contract/` and must use `isinstance(obj, SomeProtocol)` to
  verify conformance. This is what actually proves an implementation satisfies its Protocol
  at runtime — `typing.Protocol` gives no static guarantee on its own (see
  [docs/adr/0002-contracts-and-plugins.md](docs/adr/0002-contracts-and-plugins.md)).

## Running tests

```bash
pytest tests/unit            # fast, no external services
python scripts/check_layering.py  # architecture import audit
pytest tests/integration     # requires Qdrant running locally
pytest tests/contract        # protocol conformance
pytest tests/e2e             # full pipeline, requires LLM API key
```

Claude Code users can run `/qa-v1` for the local V1 gate.
Codex users should follow `AGENTS.md` and default to independent review unless
asked to implement.

## Adding a new component (example: new chunker)

1. Verify `contracts/chunking.py` Chunker Protocol covers your interface (or extend it + write ADR).
2. Create `src/modular_rag/ingestion/chunkers/my_chunker.py` implementing `chunk()` and `name()`.
3. Register in `orchestration/_default_factories.py`:
   ```python
   reg.register("chunker", "my-chunker", lambda cfg: MyChunker(**cfg.config))
   ```
4. Use in a manifest:
   ```yaml
   chunker:
     type: my-chunker
     config:
       my_param: value
   ```
5. Write tests: `tests/unit/ingestion/chunkers/test_my_chunker.py` + `tests/contract/test_chunker_conformance.py`.

## Merge Request checklist

- [ ] New code has tests (unit + contract if applicable)
- [ ] No cross-domain imports introduced
- [ ] Local V1 gate run (`/qa-v1` or Ruff + unit + contract + layering audit)
- [ ] High-risk AI-generated changes reviewed by a second provider or human reviewer
- [ ] New adapter registered in `_default_factories.py`
- [ ] `docs/architecture/` updated if layering or contracts changed
- [ ] ADR written if a structural decision was made
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
