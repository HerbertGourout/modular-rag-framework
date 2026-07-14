# Changelog

All notable changes are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added — 2026-07-12 (`feature/v1-sota-alignment`)
- `Parser` Protocol (`contracts/parsing.py`) + DOCX and HTML parsers; PDF parsing switched from pypdf to pymupdf.
- Weighted Reciprocal Rank Fusion (`weights` parameter, defaults reproduce unweighted RRF); `HybridRetriever` passes manifest weights through.
- `examples/hybrid_search/`: retrieval-only demo comparing vector-only / BM25-only / RRF-fused results (no LLM key required).
- Research digests (`docs/research/DIGEST-*.md`): 39 arXiv papers distilled into 7 actionable domain digests, wired into 8 Claude Code skills and CLAUDE.md coding rule 8 ("state of the art first").
- Test coverage: CrossEncoderReranker (unit + contract), both generators, citations builder, lexical gate, parsers — 124 → 191 tests.
- `docs/guides/code-walkthrough.md`: progressive reading guide to navigate the codebase.

### Changed — 2026-07-12 (state-of-the-art alignment)
- Chunkers now size in **tokens** (pluggable counter; whitespace default, tiktoken opt-in) with defaults 512/128 (25% overlap, arXiv:2604.12047); `AdaptiveChunker` merges fragments < 100 tokens (arXiv:2603.25333).
- `BasicSecurityGuard`: 5 → 12 injection patterns across 3 documented families (arXiv:2505.06579, 2604.12201); `check_answer` implemented — blocks answers containing URLs absent from citations (corpus-poisoning marker).
- Generator system prompts add a negative-rejection clause ("say you don't know", arXiv:2404.10981 §7.1); citation passages truncate at sentence boundaries (arXiv:2506.10408).
- `GroundednessValidator` reframed as a lexical-support gate (not a faithfulness metric); unsourced constants (`rrf_k=60`, 0.7/0.3 fusion weights, `temperature=0.1`) documented as engineering priors to tune on the V1.1 golden set.
- Lint debt cleared: `scripts/check.sh full` now passes (47 pre-existing ruff errors fixed).

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
