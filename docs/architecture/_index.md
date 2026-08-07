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

This folder documents the **target** state of the architecture, including for versions V2
through V5 not yet delivered. The real status of each capability (delivered / in progress /
planned) is in [../../ROADMAP.md](../../ROADMAP.md) — don't confuse "documented" with
"implemented."
