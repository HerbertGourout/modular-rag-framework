# Manifest Presets — Runnable vs. Blueprint

Each file under `presets/` carries a `# Status:` comment at the top with the specific reason.
This table is the quick-reference version. Classification method: read every `type:` value
against `orchestration/_default_factories.py`'s registered names, and check whether
`ComponentRegistry.wire()` (`orchestration/registry.py`) actually processes every field the
manifest declares — a field can be present in the YAML and still be silently ignored if `wire()`
never reads it.

| Preset | Status | Why |
|---|---|---|
| `local-hybrid-rag.yaml` | **Runnable** | Only V1 components; every type is registered and every field is wired. Validated in CI (`scripts/check.sh full` — see `docs/refactoring-plan.md` Lot 5). Used by `examples/simple_qa/`. |
| `secure-enterprise-rag.yaml` | Blueprint | `policies:` points at two files that don't exist (`manifests/policies/` is empty) and `wire()` never reads the `policies` field regardless; `indexer.config.url` uses `${QDRANT_URL}` interpolation that `load_manifest()` doesn't perform. |
| `agentic-rag.yaml` | Blueprint | `planner`/`agents` declared but `wire()` never processes either field — silently no-ops, not an error. V2 scope, delegated per [ADR-0005](../docs/adr/0005-document-ai-control-plane-boundary.md). |
| `graph-memory-rag.yaml` | Blueprint | `graph_store`/`planner`/`agents` all unprocessed by `wire()`. V3 scope, delegated per ADR-0005. |
| `multimodal-rag.yaml` | Blueprint | `embedder.type: multimodal` isn't a registered factory at all — `wire()` raises `RegistryError` immediately, before reaching any of the V5-only fields. |

**"Blueprint" means**: safe to read as a design sketch of what a V2/V3/V4/V5 manifest might one
day declare; do not expect `load_pipeline()` to succeed against it today. None of them are
secretly half-working — `local-hybrid-rag.yaml` is the only preset that wires end-to-end.

**Extending this table**: if you add a new preset, or if a registry change makes one of the
blueprint presets partially or fully wire-able, update both the `# Status:` comment in the file
and this table in the same change — they must not drift apart again.
