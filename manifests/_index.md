# Manifests — Configuring a pipeline without writing Python

A manifest is a YAML file that describes a complete RAG pipeline: which chunker, which
embedding model, which vector store, which retriever, which reranker, which generator, which
security guard, which telemetry. It's the central piece of the framework's philosophy (see
[CLAUDE.md](../CLAUDE.md), rule 03): **a component is only active if it's declared in a
manifest** — there is no hidden wiring in the Python code that the YAML configuration
wouldn't make visible.

**Why this choice over a classic Python configuration?** Three concrete reasons:
1. A lead or a project manager on the client side can read and edit a manifest without ever
   opening a `.py` file — the barrier to adjusting a pipeline drops to zero.
2. Switching LLM providers (moving from GPT-4o to Claude, or to an on-premise model) becomes
   a one-line YAML change, never a code change — the central argument for the vendor
   independence highlighted in [docs/business-case.md](../docs/business-case.md).
3. A manifest versioned in Git is, on its own, the living documentation of "exactly which
   pipeline runs for which client" — useful for audits or regression debugging.

## How a manifest becomes a runnable pipeline

The full path (detailed in
[docs/architecture/overview.md](../docs/architecture/overview.md), section 9) is: the YAML is
resolved (`${VAR}`/`secret://` interpolation, `app/config_resolution.py::resolve_manifest()`),
validated, then `orchestration/registry.py` maps each declared `type:` to the matching concrete
class (via the factories registered in `app/default_factories.py`), and the result is a
`Container` of ready-to-use instances that `RAGEngine` (native) or a `DocumentEngine` adapter
(delegated, per `engine.adapter`) uses to answer questions.

## `presets/` — ready-to-use, Runnable configurations

**Authoritative status table: [`README.md`](README.md).** Since
[ADR-0007](../docs/adr/0007-layer-boundaries-and-control-plane-activation.md) (Étape 7), every
file under `presets/` loads, validates, and wires cleanly — non-executable sketches live under
[`blueprints/`](blueprints/) instead, never `presets/`.

| Preset | Version | Use case | Native or delegated (ADR-0005) |
|---|---|---|---|
| [`local-hybrid-rag.yaml`](presets/local-hybrid-rag.yaml) | V1 | Local development: no authentication, lightweight models (GPT-4o-mini, bge-small), Qdrant on localhost. Recommended starting point for any new contributor or quick demo. | Native |
| [`secure-enterprise-rag.yaml`](presets/secure-enterprise-rag.yaml) | V2 | Enterprise deployment: tenant isolation, PII redaction, inline policy engine, durable Postgres audit trail, blocking quality gate. Requires `QDRANT_URL`/`QDRANT_API_KEY`/`AUDIT_DATABASE_URL` env vars and reachable Postgres/Qdrant to actually run. | Native |
| [`langgraph-rag.yaml`](presets/langgraph-rag.yaml) | V2 | Multi-step questions routed through `engine.adapter: langgraph` — a real `LangGraphEngineAdapter`, not a native agent runtime. Renamed from `agentic-rag.yaml`; the native five-agent design its old field names implied was removed in Lot 17. | Delegated |

## `blueprints/` — design sketches, not loadable

See [`README.md`](README.md) for the full table. `graph-memory-rag.yaml` and
`multimodal-rag.yaml` live here — both use fields the active V2 schema no longer accepts
(`graph_store`, `planner`, `agents`) or reference unregistered types (`embedder.type:
multimodal`), and describe capabilities (GraphRAG traversal, VLM execution) delegated per
ADR-0005 §5.2 rather than built natively. Do not pass these to `resolve_manifest()` expecting
success.

To choose a preset for a client engagement, see also
[docs/onboarding.md](../docs/onboarding.md), section 2.3 (consultant / delivery lead
profile).

## `dev/`, `staging/`, `production/` — per-environment overrides

These three folders are **deliberately empty stubs** at this stage (V4 scope — see
[CLAUDE.md](../CLAUDE.md), section 09). The idea, once built, is to allow a per-environment
override on top of a base preset (e.g., `secure-enterprise-rag.yaml` as the base, with a
`production/overrides.yaml` that tightens security further) without duplicating the entire file.
See each subfolder for the detail of what's planned: [dev/_index.md](dev/_index.md),
[staging/_index.md](staging/_index.md), [production/_index.md](production/_index.md).
