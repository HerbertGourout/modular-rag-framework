# Changelog

All notable changes are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Full `src/modular_rag/` implementation: contracts, core models, orchestration engine, ingestion pipeline, hybrid retrieval (vector + BM25 + RRF), cross-encoder reranker, OpenAI and Anthropic generators, basic security guard, PII redactor, evaluation scorers, multi-agent stubs (coordinator, extractor, synthesizer, validator), knowledge graph (networkx), EvoRAG graph versioning, CLI (`mrag ask`, `mrag ingest`), FastAPI REST endpoint.
- Five populated YAML manifest presets: `local-hybrid-rag`, `secure-enterprise-rag`, `agentic-rag`, `graph-memory-rag`, `multimodal-rag`.
- Three Architecture Decision Records: ADR-0001 (modular architecture), ADR-0002 (contracts + plugins), ADR-0003 (security + governance).
- `docs/architecture/overview.md`: full technical specification V1→V5.
- `docs/architecture/module-model.md`: layer boundaries.
- `docs/architecture/runtime-flow.md`: sequence and flow diagrams.
- `docs/architecture/security.md`: attack surfaces and guard chain.
- `ROADMAP.md`: V1→V5 milestones with checkboxes.
- `CONTRIBUTING.md`: setup, rules, step-by-step guide to add a component.
- `CLAUDE.md`: guidance for Claude Code sessions.
- `pyproject.toml`: full dependency groups (v1, v3, v4, v5, dev).

### Changed
- `README.md`: refactored to declare pre-alpha status, add "Why this framework?" section, target API snippets, Apache 2.0 licence.

## [0.0.1] — 2026-05-20

### Added
- Initial project scaffold: directory tree, empty modules, manifests, docs, ADR, `.gitlab/` templates.
- `README.md` (initial version).
