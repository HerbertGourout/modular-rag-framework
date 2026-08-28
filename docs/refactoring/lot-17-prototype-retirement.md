# Lot 17 — Prototype Retirement and Documentation Consolidation

**Date:** 2026-08-05
**Status:** COMPLETE — one sub-item blocked by the permission system, not by decision

## Scope (from `docs/refactoring-plan.md` §5, Phase D)

> Audit imports and consumers, then deprecate, retain, or remove generic agents,
> FlowCompiler/router paths, graph memory/versioning, unused future manifests, stale GitLab
> assets, and unused dependencies. Complete Claude/documentation consolidation and a research
> evidence catalogue. Keep digests; stop adding large binaries. Do not rewrite Git history in
> this lot.

## Method

Per §8.8's migration principle ("Removal: require non-use evidence, dependency/import search,
deprecation where public, release notes, and a tested restoration commit/artifact"), every
removal below was preceded by a full `grep -rln` consumer/test search across `src/`, `tests/`,
`docs/`, `examples/`, `manifests/` — not assumed from the module's name or its own
`.claude/rules/*.md` framing. Restoration path for everything removed is git history; this lot
does not rewrite it (§8.9 — verified: only new commits, no `rebase`/`filter-repo`/force-push).

## Removed (zero test coverage, zero consumers, superseded by ADR-0005 §5.2)

| Item | Evidence |
|---|---|
| `agents/coordinator/coordinator.py`, `extractor/extractor.py`, `retriever/retriever_agent.py`, `synthesizer/synthesizer.py`, `validator/validator.py` (5 classes) | Zero test files, zero consumers anywhere (only self-exported via `agents/__init__.py`). Implemented exactly the generic multi-agent orchestration ADR-0005 §5.2 delegates to the external engine, predating that decision. |
| `contracts/agents.py` (`Agent`, `AgentResult`, `AgentTask`) | Zero test, zero consumer besides `contracts/__init__.py`'s own re-export. The Protocol definition for the same delegated capability. |
| `core/enums.AgentRole` | Only consumer was `contracts/agents.py` (removed) and its own declaration. |
| `orchestration/flow_compiler.py` (`FlowCompiler`) | Zero test, zero consumer — `compile()` had no caller anywhere. |
| `orchestration/router.py` (`QueryRouter`) | Zero test. `RAGEngine.__init__` constructed a `QueryRouter` but **never called `.route()` on it anywhere** — verified by grepping `engine.py` for `self._router.` (zero matches). Its classification never influenced which pipeline steps ran. |
| `core/enums.RoutingStrategy` | Only consumers were `router.py`, `flow_compiler.py`, `retrieval/planners/*`, `contracts/planning.py` — all removed alongside it. |
| `core/models/query.py`'s `routing_hint` field (+ its test) | Only ever read by `router.py` (removed). A public `Query` field, but pre-alpha (`version = "0.0.1"`) with no external documented consumer — see "Compatibility note" below. |
| `retrieval/planners/graph.py`, `retrieval/planners/simple.py` | Zero test, zero consumer — `registry.py`'s `"planner"` role slot has zero registered factories and `wire()` never reads `manifest.planner` (already documented as such in `manifests/README.md`'s blueprint classification, unchanged by this lot). |
| `contracts/planning.py` (`ExecutionPlan`, `ExecutionStep`, `Planner`) | Consumers were exactly the five items above, all removed. |
| `memory/versioning/graph_versioning.py` (`GraphVersionManager`, EvoRAG) | Zero test, zero consumer besides `memory/__init__.py`'s re-export. Reached into `KnowledgeGraph`'s private `_edges` attribute (never a clean integration). Implements the delegated fine-tuning-execution capability (ADR-0005 §5.2), not the drift-detection/evaluation-trigger half that stays native. |
| `pyproject.toml`'s `v3` (Graph Memory) optional-dependency group (`neo4j`, `networkx`, `spacy`, `python-louvain`) | Zero imports anywhere in `src/modular_rag/` for any of the four packages — verified before removal. Backed the native GraphRAG traversal/community-detection/NER build ADR-0005 §5.2 delegates. `all` extra updated (`v1,v3,v4,v5,langgraph,dev` → `v1,v4,v5,langgraph,dev`). |

**Compatibility note on `routing_hint`**: this is a public Pydantic model field, and §9's
checklist asks that "public and persisted compatibility surfaces have policies and tests." It
was removed outright rather than deprecated-then-removed because: (a) the project is pre-alpha
(`Development Status :: 2 - Pre-Alpha`, version `0.0.1`), (b) it is unreachable from the REST
API (`QuestionRequest` has only `question`) and the CLI (`ask` has no `--routing-hint` flag) —
only a direct Python caller of `RAGEngine.answer(question, routing_hint=...)` could have set it,
and would have received zero observable effect since nothing read it, (c) git history is the
restoration path per §8.9. This is a smaller-blast-radius case than, say, removing a `tenant_id`
field would be.

## Retained, with a documented caveat

**`memory/graph/knowledge_graph.py`** (`KnowledgeGraph`, `GraphNode`, `GraphEdge`) — the one
item on the audit list this lot did **not** remove. It differs from everything above in one
material way: it has real test coverage (`tests/unit/memory/test_knowledge_graph.py`), so it
was not treated as a zero-evidence dead prototype. It is still zero-consumer outside its own
test (not wired into any retriever or pipeline). Its `neighbours()`/`subgraph_for_query()`
methods are genuine multi-hop-traversal/sub-graph-selection logic — exactly the GraphRAG
capability ADR-0005 §5.2 delegates — not a passive data model, so this is not a clean "retain,
it's just a data model" case either. `docs/architecture/structure.md`'s own pre-existing note
hedged this as "contingent on Lot 6 evidence, not decided yet" — Lot 6 (the LangGraph/LlamaIndex
Workflows spike, ADR-0006) never actually produced evidence bearing on this specific question,
so it remains genuinely undecided. Retained rather than removed given the test coverage and the
open question; documented with an explicit caveat directly in the module's own docstring and in
`docs/architecture/structure.md`, rather than silently kept as if fully resolved.

Also corrected a false claim in its docstring ("using networkx") — it is plain Python dict/list and
never imported `networkx`.

## Blocked, not decided: stale GitLab assets

`.gitlab-ci.yml` and `.gitlab/` (issue/MR templates, an empty `ci/templates/.gitkeep`) are
exactly what `CLAUDE.md` itself already flagged for "removal consideration in Lot 17" — the
repo's actual remote is GitHub, `.gitlab-ci.yml` has never run against it, and it duplicates a
strictly weaker, non-blocking version of what `.github/workflows/ci.yml` now does (7 jobs vs.
its 3, including the exact `mypy ... || true` non-blocking bug Lot 3 fixed in the real CI).
Herbert Gourout explicitly confirmed removal (via an in-session question) before any attempt.
Two separate `rm`/`git rm` attempts were both denied by the permission system — `.gitlab/**`
and `.gitlab-ci.yml` are only in `settings.json`'s `Edit`/`Write` deny list (verified by
reading it directly), so the block is coming from something else (a hook, or a Bash-level deny
pattern not visible from `settings.json` alone). Per this session's own instruction not to
retry an identical blocked action, this was not forced through. **Left in place, not by
decision but by an unresolved permission block** — the next session with visibility into
whatever is actually blocking it (or a `.claude/settings.json` change) should complete this.

## Manifests: no action needed

`manifests/dev/`, `manifests/staging/`, `manifests/production/` are documentation-only stub
`_index.md` files that already accurately self-describe as "V4, not yet implemented" — not
dead code or misleading claims, so not a retirement candidate. `manifests/policies/` does not
exist as a directory at all; its only reference is `secure-enterprise-rag.yaml`'s already-
documented broken `policies:` field (Lot 5, `manifests/README.md`), unchanged by this lot.

## Documentation consolidation

Corrected stale references to every item removed above, across:

- `docs/architecture/structure.md` — enum table (7 → 5 `StrEnum`s), `Query` fields table,
  the `agents/` section (rewritten to describe the current delegation-adapter framing),
  `memory/graph/knowledge_graph.py`'s section (added the retain-with-caveat note),
  `orchestration/router.py`/`flow_compiler.py`'s section (replaced with a removal note), and
  — found while correcting this file — `app/settings.py`'s section previously claimed
  `MRAG_*` env vars work; added the same "never actually called anywhere" finding from Lot 16c.
- `docs/architecture/module-model.md` — the module tree diagram and the `contracts`/`core`
  symbol-inventory table.
- `docs/architecture/data-model.md` — `Query`'s field table and code example.
- `docs/architecture/roadmap-mermaid.md` — added a "historical design reference, not current
  behavior" banner to the V2 agentic-runtime section (kept the diagram itself — roadmap intent
  has documentary value even where the code is gone).
- `docs/guides/working-with-agents.md` — added a superseded-by-ADR-0005 banner (561 lines of
  V2+ implementation guidance; not rewritten, matching the `.claude/rules/agentic_workflows.md`/
  `agents.md` precedent from Lot 2 of banner-not-delete for design-reference content).
- `docs/guides/installation.md` — the extras-group table was stale beyond just `v3`: `v4`
  claimed "OPA bindings, policy validators" and `v5` claimed "PIL, whisper, timm," neither of
  which matches `pyproject.toml`'s actual declared packages (opentelemetry-*/pymupdf+pillow+
  pytesseract respectively). Corrected against the real file, and added the new `langgraph`/
  `supply-chain` groups (Lots 15/16b) this table had never listed.
- `docs/glossary.md` — `EvoRAG` entry now states the implementation was removed; kept the
  concept definition since it remains a real V3 design reference.

Not touched, deliberately: `docs/refactoring/lot-2-claude-realignment.md` (a point-in-time
decision record — editing it would misrepresent history) and `docs/research/DIGEST-*.md`'s
substance (research findings, not implementation claims — per this lot's own "keep digests"
instruction).

## Research evidence catalogue

New `docs/research/EVIDENCE-CATALOGUE.md` — a per-paper index of all 56 files under
`.claude/research-papers/`, cross-referencing every `## [arXiv-id] Title` header across all
seven `DIGEST-*.md` files against the actual filenames on disk (not by re-reading all 56 PDFs,
which is out of scope — that is the specialist-agent digest-generation process
`docs/research/README.md` already documents separately).

Found and recorded, via `md5sum`, that the corpus is **56 files but only 55 unique papers**:
`2604.11623v3.pdf` is byte-identical in both `advanced_architecture/` and `agentic/`.

Also resolved an apparent inconsistency in `DIGEST-retrieval.md`'s own header ("4 arXiv PDFs"
when `retrieval/` holds only 3 files): the 4th is a legitimate cross-citation of a
`security/`-folder paper (2603.21654), not a missing or misplaced file — corrected the header to
say so explicitly.

38 of 55 unique papers have a digest entry; the remaining 17 (`agentic/`, `graph_rag/`,
`multimodal_rag/`) are listed by arXiv id only, matching `docs/research/README.md`'s existing
"deferred per roadmap discipline" policy — not distilled in this lot, which would be scope creep
into V2/V3/V5 work.

Redistribution rights remain exactly where Lot 16b left them (escalated, "leave as-is for now"
per Herbert Gourout) — the catalogue documents provenance, it does not re-open or resolve that
decision.

## Verification

`./scripts/check.sh full` — all 7 steps pass (mypy baseline unaffected, 31/31; 464 unit + 82
contract tests unaffected — removing `routing_hint` deleted exactly one test,
`test_query_routing_hint_optional`, with no replacement needed since the field no longer
exists). `pip install -e ".[all]"` succeeds cleanly after the `v3` extra removal.

## Tracker updates

- Header status block: Lot 17 → COMPLETE, one sub-item (GitLab assets) blocked.
- Gap matrix: "Prototype retirement" and "Research assets" rows resolved (with the GitLab caveat
  noted on the former).
- Decision log + change history: new Lot 17 entry.
