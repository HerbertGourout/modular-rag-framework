# Architecture — Overview

This folder is the framework's technical specification: not "how to configure a pipeline"
(that's [../guides/](../guides/)), but "how the system is built and why." If you're trying
to understand the code before changing it, or to defend a structural choice in front of a
client architect, this is where the answer lives — complemented by the "why" captured in the
[ADRs](../adr/_index.md).

## How to navigate by question

| Your question | Document |
|---|---|
| "What's the overall vision, and what does each V1→V5 version do?" | [overview.md](overview.md) |
| "Which capabilities really execute today, and through which entry point?" | [capability-matrix.md](capability-matrix.md) |
| "What data objects flow through the pipeline, with what fields and invariants?" | [data-model.md](data-model.md) |
| "What modules exist, and why can't they import from each other?" | [module-model.md](module-model.md) |
| "What happens, step by step, when a query is processed?" | [runtime-flow.md](runtime-flow.md) |
| "What attacks does the framework cover, and with what exact mechanisms?" | [security.md](security.md) |
| "What are the assets, trust boundaries, and threats, and which are still open?" | [threat-model.md](threat-model.md) |
| "How is data classified, and what's the PII/tenant schema?" | [data-classification-policy.md](data-classification-policy.md) |
| "How does selecting a native vs. an external engine (LangGraph) actually work?" | [document-engine-contract.md](document-engine-contract.md) |
| "I want the exhaustive map of every file in the repo, with its role" | [structure.md](structure.md) |
| "I want to visualize the roadmap and the flows as diagrams" | [roadmap-mermaid.md](roadmap-mermaid.md) |

## Recommended reading order for a new technical contributor

1. [overview.md](overview.md) — the general framework, read in full once.
2. [capability-matrix.md](capability-matrix.md) — to distinguish operational, programmatic,
   blueprint, delegated, and unresolved capabilities.
3. [module-model.md](module-model.md) — to internalize the dependency rule before touching
   the code.
4. [data-model.md](data-model.md) — to recognize the objects handled everywhere
   (`Document`, `Chunk`, `Query`, `Answer`, `Trace`...).
5. [runtime-flow.md](runtime-flow.md) — to visualize the full path of a request.
6. [security.md](security.md) and [structure.md](structure.md) — as reference, as needed.

This folder documents both what's built and what's still a target: V1.0 is implemented and
unit/contract-tested, while its live Qdrant/LLM validation remains pending in `ROADMAP.md`; V1.1
and V1.2 are partially built. In parallel,
a substantial slice of V2 native scope — policy-as-code enforcement, fail-closed tenant isolation,
compliance audit events, redaction, and human-in-the-loop review — is real, wired, and covered by
tests today, not merely designed. What remains a target is mostly the *delegated* capabilities
(generic multi-agent orchestration, GraphRAG traversal, multimodal execution — see
[ADR-0005](../adr/0005-document-ai-control-plane-boundary.md)) and a handful of specific
native gaps each document calls out explicitly where they exist (e.g. `AdversarialDetector`
implemented but not registered in any manifest — [security.md](security.md); classification-level
enforcement not yet built — [data-classification-policy.md](data-classification-policy.md)).
Don't assume "documented" means "implemented" for any single claim — but don't assume the
opposite either. [capability-matrix.md](capability-matrix.md) is the one document in this folder
whose entire job is drawing that operational/aspirational line precisely, capability by
capability; when in doubt, that's the page to check, not a blanket disclaimer here.
