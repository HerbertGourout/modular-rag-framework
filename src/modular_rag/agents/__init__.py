"""Per ADR-0005 §5.2 (docs/adr/0005-document-ai-control-plane-boundary.md), generic
multi-agent orchestration (coordinator/planner/retriever/extractor/synthesizer/validator
roles) is delegated to the selected external engine, not built natively. This directory
hosts the adapter integration that calls into that engine — not a native agent runtime.

Lot 17 (docs/refactoring-plan.md) removed the five pre-ADR-0005 native agent prototypes
that used to live here (CoordinatorAgent, ExtractorAgent, RetrieverAgent, SynthesizerAgent,
ValidatorAgent): each had zero test coverage and zero consumers anywhere in the codebase —
verified via a full dependency/import search before removal — and implemented exactly the
capability ADR-0005 delegates, predating that decision. Restoration path: git history (this
lot does not rewrite it). See docs/refactoring/lot-17-prototype-retirement.md for the
non-use evidence and rationale.
"""
