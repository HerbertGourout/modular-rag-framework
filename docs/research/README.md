# Research Digests — State of the Art for Feature Design

Per-paper index of all 56 files (55 unique — one duplicate, see below) and their digest status:
[EVIDENCE-CATALOGUE.md](EVIDENCE-CATALOGUE.md) (Lot 17, `docs/refactoring-plan.md`).

Actionable distillations of the arXiv corpus in `.claude/research-papers/`. **Every design decision
(fusion weights, chunking parameters, guard patterns, metric choices, architectural patterns) must
consult the matching digest and cite the arXiv id backing the choice** — see CLAUDE.md coding rule 08.
Routine implementation (tests, fixes, wiring) is exempt.

| Digest | Source folder | Feeds | Wired into skills |
|---|---|---|---|
| [DIGEST-retrieval.md](DIGEST-retrieval.md) | `retrieval/` (4 papers) | `retrieval/fusion/`, `retrieval/rerankers/` | `/design-retriever-fusion`, `/add-retriever` |
| [DIGEST-generation.md](DIGEST-generation.md) | `generation/` (3 papers) | `generation/synthesizers/`, `generation/validators/` | `/add-generator` |
| [DIGEST-chunking.md](DIGEST-chunking.md) | `chunkings_strategies/` (6 papers) | `ingestion/chunkers/` | `/optimize-chunking`, `/add-component` |
| [DIGEST-evaluation.md](DIGEST-evaluation.md) | `rag_optimisation_evaluation/` (9 papers) | `retrieval/fusion/`, V1.1 `eval/` | `/design-retriever-fusion`, `/prepare-evaluation`, `/add-retriever` |
| [DIGEST-security.md](DIGEST-security.md) | `security/` (9 papers) | `security/filters/`, `security/redaction/`, V1.2 audit | `/add-security-guard` |
| [DIGEST-overviews.md](DIGEST-overviews.md) | `overviews/` (5 surveys) | whole pipeline | `/design-retriever-fusion`, `/add-generator` |
| [DIGEST-architecture.md](DIGEST-architecture.md) | `advanced_architecture/` (3 papers) | `orchestration/`, ADRs | `/validate-architecture` |

## Gaps and deferred corpora

- Deferred per roadmap discipline: `agentic/` (distill at V2 start), `graph_rag/` (V3),
  `multimodal_rag/` (V5).
- Known V1 coverage gap (DIGEST-security item 10): membership inference and embedding inversion
  are threat classes with no current control — revisit in V1.2.
- Unsourced engineering defaults to revisit in V1.1: `rrf_k=60` (Cormack 2009, not in corpus),
  `vector_weight=0.7/bm25_weight=0.3` (tune on golden set), generator `temperature=0.1`
  (no paper addresses decoding temperature).

## Regenerating a digest

Launch the domain's specialist agent (it has read access to its paper folder) with the instruction to
read each PDF (`pages` parameter, ≤20 pages/request) and rewrite `docs/research/DIGEST-<domain>.md`:
per paper — arXiv id, thesis, actionable techniques with numbers, limitations — plus a final
"Implications for this framework" section mapped to real files, ≤300 lines.
