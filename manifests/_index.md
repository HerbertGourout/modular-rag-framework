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
[docs/architecture/overview.md](../docs/architecture/overview.md), section 9) is: the YAML
is loaded and validated by `app/bootstrap.py`, then `orchestration/registry.py` maps each
declared `type:` to the matching concrete class (via the factories registered in
`_default_factories.py`), and the result is a `Container` of ready-to-use instances that the
`RAGEngine` uses to answer questions.

## `presets/` — ready-to-use configurations

**Authoritative status table: [`README.md`](README.md)** — only `local-hybrid-rag.yaml` is
Runnable today; `secure-enterprise-rag.yaml`, `agentic-rag.yaml`, `graph-memory-rag.yaml`, and
`multimodal-rag.yaml` are all Blueprint (declared, but `ComponentRegistry.wire()` doesn't
process every field they use). This file previously carried its own copy of this table with a
different (and contradictory) description — removed to keep one source of truth. What each
preset is *intended* to eventually cover, once its blueprint is completed:

| Preset | Target version | Intended use case | Native or delegated (ADR-0005) |
|---|---|---|---|
| [`local-hybrid-rag.yaml`](presets/local-hybrid-rag.yaml) | V1 | Local development: no authentication, lightweight models (GPT-4o-mini, bge-small), Qdrant on localhost. Recommended starting point for any new contributor or quick demo. **Runnable now.** | Native |
| [`secure-enterprise-rag.yaml`](presets/secure-enterprise-rag.yaml) | V1 | Internal deployment for a client: security guards enabled, tighter `max_query_length`, generation temperature at 0. | Native |
| [`agentic-rag.yaml`](presets/agentic-rag.yaml) | V2.1 | Multi-step questions — would call an external-engine adapter (e.g. `LangGraphEngineAdapter`) through `manifest.engine.adapter`, not a native five-agent runtime. The five prototype agent classes this preset's field names once implied were removed in Lot 17. | Delegated |
| [`graph-memory-rag.yaml`](presets/graph-memory-rag.yaml) | V3.0 | Reasoning over entity relationships (GraphRAG) — traversal delegated to the external engine; a native `KnowledgeGraph` data model may be retained (undecided). | Delegated (traversal) |
| [`multimodal-rag.yaml`](presets/multimodal-rag.yaml) | V5.0 | Documents containing images, tables, or audio/video segments — VLM execution delegated; parsing/citation enrichment may stay native. | Delegated (VLM execution) |

To choose a preset for a client engagement, see also
[docs/onboarding.md](../docs/onboarding.md), section 2.3 (consultant / delivery lead
profile).

## `dev/`, `staging/`, `production/` — per-environment overrides

These three folders are **deliberately empty stubs** at this stage (V4 scope — see
[CLAUDE.md](../CLAUDE.md), section 09). The idea, once built, is to allow a per-environment
override on top of a base preset (e.g., `secure-enterprise-rag.yaml` as the base, with a
`production/overrides.yaml` that tightens security further and enables the full audit
trail) without duplicating the entire file. See each subfolder for the detail of what's
planned: [dev/_index.md](dev/_index.md), [staging/_index.md](staging/_index.md),
[production/_index.md](production/_index.md).
