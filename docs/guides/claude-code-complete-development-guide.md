---
title: "Claude Code Development Guide"
description: "Repository workflow for implementing and validating Modular RAG changes with Claude Code"
version: "2.0"
lastUpdated: "2026-09-02"
audience: ["Developers", "Architects", "Tech Leads"]
---

# Claude Code Development Guide

This guide explains how to use the repository's existing instructions, contracts, composition
root, tests, and review handoff. It intentionally avoids duplicating complete component APIs;
source contracts and module-level `CLAUDE.md` files are authoritative.

## 1. Establish the current scope

Before editing:

1. read root `CLAUDE.md` and `AGENTS.md`;
2. read the `CLAUDE.md` in each affected source module;
3. inspect the relevant contract, implementation, manifest, and tests;
4. distinguish current behavior from roadmap proposals;
5. read the applicable accepted ADR.

ADR-0015 is accepted, but its engine-independent assurance levels and external-application
boundary are not implemented APIs. Lot 20 provider-egress enforcement and planned Lots 21–22
must not be implemented opportunistically inside unrelated work; Lot 21 also requires its focused
contract ADR.

## 2. Preserve the architecture

The repository uses hexagonal boundaries:

- `core/` imports only `core/`;
- `contracts/` imports `core/` and `contracts/`;
- a domain imports `core/`, `contracts/`, and itself;
- `adapters/` imports `core/`, `contracts/`, and `adapters/`;
- `orchestration/` imports `core/`, `contracts/`, and `orchestration/`;
- `app/` is the composition root and may wire concrete domains/adapters;
- `api/` and `cli/` enter through `app/`.

Verify this mechanically:

```powershell
.\.venv\Scripts\python.exe scripts\check_layering.py --strict
```

Do not add a cross-domain import because two components happen to collaborate. Put shared data in
`core/models/`, behavior boundaries in `contracts/`, and coordination in `orchestration/` or
`app/` according to the dependency rules.

## 3. Add or change a built-in component

For a new chunker, retriever, generator, guard, adapter, or governance component:

1. confirm that an existing Protocol expresses the required behavior;
2. if the contract must change, obtain an accepted ADR and plan migration/conformance first;
3. implement in the owning domain or adapter package;
4. use lazy imports for optional heavy dependencies;
5. register the built-in in `src/modular_rag/app/default_factories.py`;
6. select it using the existing manifest schema;
7. add unit, conformance, factory, and manifest tests as applicable;
8. update the relevant reference documentation.

There is no `COMPONENT_REGISTRY` global and no `registry.get_component()` API. The real flow is:

```python
from modular_rag.app.bootstrap import load_pipeline

pipeline = load_pipeline("manifests/presets/local-hybrid-rag.yaml")
answer = pipeline.answer("What evidence supports this conclusion?")
```

For lower-level tests or composition work, use `create_default_registry().wire(manifest)`.

## 4. Use the real contracts

Always open the Protocol before writing an implementation. Representative current shapes include:

```python
# SecurityGuard
def check_query(self, query: Query) -> GuardResult: ...
def check_answer(self, answer: Answer) -> GuardResult: ...
def name(self) -> str: ...

# Retriever
def retrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]: ...
async def aretrieve(self, query: Query, k: int = 10) -> list[RetrievedChunk]: ...
def name(self) -> str: ...

# Generator
def generate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer: ...
```

`GuardResult` uses `allowed`, not `is_safe`. `TraceStep` uses `name`, token counts,
`latency_ms`, and `metadata`; it has no `component`, `operation`, or mutable `output` field.

## 5. Understand the execution boundary

The native `RAGEngine` executes a fixed governed sequence: tenant check, policy check, query
guard, retrieval, tenant filtering, optional reranking, generation, answer guard, redaction, and
optional human-review queueing. Feedback recording and offline evaluation are separate operations.

`LangGraphEngineAdapter` is an optional `DocumentEngine` implementation, not the framework's
architecture. It supports tenant isolation, guards, redaction, streaming, cancellation, and a
governance intercept. Native-only controls are rejected during manifest validation rather than
silently ignored. See `docs/architecture/document-engine-contract.md`.

## 6. Treat sensitive data honestly

- Never log raw queries, answers, documents, corrections, credentials, or provider payloads.
- Redact before storing free-text audit or feedback fields.
- Keep tenant and policy decisions fail-closed.
- Do not claim that current guards provide provider-egress authorization or regulatory
  certification.
- Until Lot 20 ships, use deployment controls or approved local providers when classified data
  must not reach an external API.

Read `docs/architecture/security.md`, `data-classification-policy.md`, and `threat-model.md` for the
current control boundary.

## 7. Evaluation and documentation

Evaluation is offline per ADR-0008. Extend the existing golden set, scorers, benchmark runner,
reports, and quality gate; do not introduce an evaluation manifest component. Use
`.claude/skills/prepare-evaluation/SKILL.md` for the current workflow.

Documentation must label each claim as current, delegated, proposed, planned, or historical where
ambiguity is possible. The code is the primary source for current behavior; accepted ADRs remain
the source for intentional constraints and decisions.

## 8. Validate proportionately

Start with affected tests, then run the standard checks:

```powershell
.\scripts\check.ps1 quick
.\scripts\check.ps1 full
```

The full command includes linting, strict layering, documentation validation, tests, contract
tests, and the offline quality gate. Provider-backed integration/e2e checks require confirmed
services and credentials and are not run implicitly.

Before handoff, also inspect:

```powershell
git diff --check
git status --short
```

Do not update a golden baseline, loosen a security threshold, or accept a compatibility break only
to make validation pass.

## 9. Review workflow

Claude Code is the writer and runs local QA. Codex reviews the immutable task diff in two bounded
passes. Pass 1 discovers material findings; Claude addresses accepted findings. Pass 2 verifies
closure and corrective-diff regressions only. After pass 2, Claude performs the documented final
remediation/validation handoff and a human makes the merge or release decision. See
`docs/guides/ai-engineering-workflow.md` for the exact prompts and artifacts.

## Reference map

- Architecture: `docs/architecture/overview.md`, `module-model.md`, `runtime-flow.md`
- Component registration: `src/modular_rag/app/default_factories.py`
- Runtime manifests: `manifests/README.md`
- Security: `src/modular_rag/security/CLAUDE.md`
- Orchestration: `src/modular_rag/orchestration/CLAUDE.md`
- Contracts: `src/modular_rag/contracts/CLAUDE.md`
- Evaluation: `docs/guides/offline-evaluation.md`
- Contribution workflow: `CONTRIBUTING.md`
