# Contributing

## Before you start

1. Read [CLAUDE.md](CLAUDE.md) — it documents the architectural rules you must follow.
2. Read [docs/architecture/overview.md](docs/architecture/overview.md) — the technical specification.
3. Read the relevant ADR(s) in [docs/adr/](docs/adr/) for the area you are modifying.

## Development setup

```bash
git clone https://pscode.lioncloud.net/data_specialiste/advancedpublicisrag.git
cd advancedpublicisrag/modular-rag-framework
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e .[v1,dev]
```

## Code rules

- **Contracts first**: add or update the Protocol in `contracts/` before writing an implementation.
- **No cross-domain imports**: `ingestion/` must not import from `generation/`. Both communicate through `contracts/` and `core/models/`.
- **Register in `_default_factories.py`**: every new built-in adapter must be registered by type name.
- **Tests mirror `src/`**: `tests/unit/ingestion/chunkers/test_fixed.py` mirrors `src/modular_rag/ingestion/chunkers/fixed.py`.
- **Contract tests** go in `tests/contract/` and must use `isinstance(obj, SomeProtocol)` to verify conformance.

## Running tests

```bash
pytest tests/unit            # fast, no external services
pytest tests/integration     # requires Qdrant running locally
pytest tests/contract        # protocol conformance
pytest tests/e2e             # full pipeline, requires LLM API key
```

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
- [ ] New adapter registered in `_default_factories.py`
- [ ] `docs/architecture/` updated if layering or contracts changed
- [ ] ADR written if a structural decision was made
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
