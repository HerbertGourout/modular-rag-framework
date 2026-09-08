# Manifest Presets — Runnable vs. Blueprint

Since [ADR-0007](../docs/adr/0007-layer-boundaries-and-control-plane-activation.md) (Étape 7),
`manifests/presets/` contains **only** configurations that pass load, capability validation, and
a wiring smoke test — non-executable design sketches live in `manifests/blueprints/` instead and
are never loaded through `resolve_manifest()`/`mrag validate`/`mrag ask`.

Classification method: read every `type:` value against `app/default_factories.py`'s registered
names, and check whether `ComponentRegistry.wire()` (`orchestration/registry.py`) actually
processes every field the manifest declares.

## `manifests/presets/` — Runnable

| Preset | Notes |
|---|---|
| `local-hybrid-rag.yaml` | V1, native engine. Only V1 components; every type is registered and every field is wired. Validated in CI (`scripts/check.sh full`). Used by `examples/simple_qa/`. |
| `secure-enterprise-rag.yaml` | V2, native engine. Governance (`tenant_enforcement`, `redactor`, inline `policy_engine`, Postgres `audit_sink`, `feedback_sink`, `review_queue`) plus telemetry; `${QDRANT_URL}`/`secret://QDRANT_API_KEY`/`secret://AUDIT_DATABASE_URL` resolve via `app/config_resolution.py`. Offline golden-set/drift jobs are intentionally not runtime fields (ADR-0008/0014). `retriever.config.lexical: sparse-qdrant` selects a second dedicated Qdrant collection for durable/multi-worker lexical retrieval. Requires the env vars and reachable PostgreSQL/Qdrant. Classification-aware provider egress (Lot 20, `governance.egress_policy`) is implemented but opt-in — this shipped preset does not enable it; see `docs/refactoring/lot-20-data-classification-egress-control.md`. |

No manifest currently wraps an arbitrary existing LangChain/LangGraph application. The shipped
`langgraph-rag.yaml` builds the repository's fixed graph; accepted ADR-0015 plans a different
existing-application adapter for Lot 22, which is not implemented.
| `langgraph-rag.yaml` | V2, `engine.adapter: langgraph`. Renamed from `agentic-rag.yaml` — the old `planner`/`agents` fields described a native multi-agent runtime that was never built (removed as dead code in Lot 17). The current adapter is a fixed route → retrieve → guard → generate graph; planning, tool use, decomposition and collaborating agents remain delegated targets, not current behaviour. |

None of the three shipped presets enables `observability.tracer` or `observability.meter`. Both
roles are registered and tested, but require a custom manifest today. Also note that
`validate_capabilities()` does not yet check those two role names; wiring remains the definitive
validation step for them.

Each file also carries its own `# Status:` header comment with the same information, kept in
sync with this table by convention — if you add a preset or convert a blueprint, update both in
the same change.

## `manifests/blueprints/` — Design sketches, not loadable

| Blueprint | Why it's not runnable |
|---|---|
| `graph-memory-rag.yaml` | GraphRAG traversal is delegated per ADR-0005 §5.2, and the selected engine does not provide graph-memory retrieval today. The zero-consumer native graph prototype was removed in ADR-0007 Étape 8. Uses pre-V2 fields that the active schema rejects. |
| `multimodal-rag.yaml` | `embedder.type: multimodal` isn't a registered factory. VLM execution is delegated per ADR-0005 §5.2 — the native modality-agent fields this file used to carry were removed. Only the parsing/citation-enrichment sketch remains, and that capability's native-vs-delegated status is itself still an open decision. |

**"Blueprint" means**: safe to read as a design sketch of a future capability; `resolve_manifest()`
will reject these outright (unknown/removed fields, unregistered types) rather than silently
no-op. None of them are secretly half-working.

**Extending this table**: if you add a new preset, move a blueprint into `presets/`, or move a
preset back to `blueprints/`, update both the `# Status:` comment in the file and this table in
the same change — they must not drift apart again.
