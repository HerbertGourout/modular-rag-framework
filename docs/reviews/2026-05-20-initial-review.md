# Initial review — Project structure & README

**Date:** 2026-05-20
**Author:** Collaborative review (Herbert + Claude)
**Target:** `modular-rag-framework` at commit `47a519d` (branch `initial-structure`)

---

## Context

A very ambitious technical specification for an open-source modular RAG framework with a 5-version release plan (V1 core RAG → V5 Multimodal, via agentic, graph memory, governance). This review covers the state of the repository and the README against that vision.

**Actual observed state of the repository**: it is a **complete but empty structural scaffold**. 108 lines total in the repo, **all located in the `README.md`**. All Python files, YAML manifests, and docs (architecture .md files, ADRs, guides) are at 0 lines. The latest commit is explicit: *"Add initial project structure, README"*.

The review therefore focuses on the **quality of the skeleton as a foundation** and on the **editorial quality of the README**, not on existing code.

---

## 1. Overall assessment

**Verdict: a very good scaffold, ambitious and coherent — but at this stage it is only an architectural promise. The README oversells what actually exists.**

The directory skeleton faithfully reflects the technical specification: separation of control plane / ingestion / knowledge / reasoning / safety / evaluation. The module granularity (contracts, core, orchestration, ingestion, retrieval, generation, agents, security, memory, eval, observability, adapters, cli, api) is exactly what you would expect from a framework that wants to separate interfaces from implementations.

**The main risk**: the README speaks in the present tense ("Adaptive chunking", "Hybrid retrieval", "Agentic runtime", `pipeline.answer(...)`) while not a single line of code exists. For an open-source project, that is a trust-eroding signal — a visitor who clones and runs `pip install -e .` against the empty `pyproject.toml` will get a bad first impression.

> ✅ **Action taken on 2026-05-20**: the README was reworked to honestly announce the pre-alpha status, add a "Why this framework?", settle the license on Apache 2.0, and mark the examples as "target API — not functional yet". See section 7.

---

## 2. Strengths of the current structure

### 2.1 `contracts/` split separated from implementations
Having [src/modular_rag/contracts/](../../src/modular_rag/contracts/) (chunking, embeddings, indexing, retrieval, reranking, generation, planning, agents, security, evaluation, storage, telemetry, manifests) **isolated from the rest** is exactly the right decision for a modular framework. It is what makes components swappable.

### 2.2 Distinct `adapters/` layer
[src/modular_rag/adapters/](../../src/modular_rag/adapters/) (auth, embeddings, graphstores, llms, search, vectorstores) clearly separates external integrations from the core. A good hexagonal pattern.

### 2.3 Per-environment manifests
[manifests/dev/](../../manifests/dev/), [manifests/staging/](../../manifests/staging/), [manifests/production/](../../manifests/production/) + [manifests/presets/](../../manifests/presets/) anticipates V4 (multi-environment governance) from V1 onward. Excellent.

### 2.4 Presets aligned with the roadmap
The 5 presets ([local-hybrid-rag.yaml](../../manifests/presets/local-hybrid-rag.yaml), [secure-enterprise-rag.yaml](../../manifests/presets/secure-enterprise-rag.yaml), [agentic-rag.yaml](../../manifests/presets/agentic-rag.yaml), [graph-memory-rag.yaml](../../manifests/presets/graph-memory-rag.yaml), [multimodal-rag.yaml](../../manifests/presets/multimodal-rag.yaml)) visually trace the V1→V5 path. It is an excellent contract with the roadmap.

### 2.5 Stratified tests
[tests/unit/](../../tests/unit/), [tests/integration/](../../tests/integration/), [tests/e2e/](../../tests/e2e/), [tests/contract/](../../tests/contract/), [tests/benchmark/](../../tests/benchmark/) — the presence of a `contract/` folder shows you understood the point: contracts must have **tests that verify implementations honor the interface**. That is mature.

### 2.6 ADRs + benchmarks from day one
[docs/adr/](../adr/) (numbered Architecture Decision Records) and [benchmarks/](../../benchmarks/) (configs, datasets, notebooks, results) are strong quality signals. Many RAG projects add them too late.

### 2.7 Granular agents
[agents/coordinator/](../../src/modular_rag/agents/coordinator/), [extractor/](../../src/modular_rag/agents/extractor/), [retriever/](../../src/modular_rag/agents/retriever/), [synthesizer/](../../src/modular_rag/agents/synthesizer/), [validator/](../../src/modular_rag/agents/validator/) — matches exactly the roles defined in V2 (planner/retrieval/synthesis/critic/output).

### 2.8 Memory with graph + versioning
[memory/graph/](../../src/modular_rag/memory/graph/), [memory/kv/](../../src/modular_rag/memory/kv/), [memory/versioning/](../../src/modular_rag/memory/versioning/) anticipates V3 (GraphRAG) and V4 (change management). The presence of `versioning/` is particularly clever.

---

## 3. Weaknesses and points of attention

### 3.1 ❌ Everything is empty — the README lies by omission
All the concrete promises in the README (`pipeline = load_pipeline(...)`, `pipeline.answer(...)`, examples `simple_qa`/`hybrid_search`/etc.) will not work. The `pyproject.toml` is empty → `pip install -e .` will fail.

✅ **Resolved on 2026-05-20** by the README rework (explicit pre-alpha notice).

### 3.2 ❌ No per-module `tests/`
You have the test **categories** (unit/integration/e2e/contract) but no files inside them, and **no mirror structure** of `src/modular_rag/`. When hundreds of modules appear, finding a component's test will become painful. Preparing `tests/unit/contracts/`, `tests/unit/orchestration/`, etc. (mirroring `src/`) now would avoid a restructuring later.

### 3.3 ❌ No runnable `examples/` and no minimal `pyproject.toml`
The 5 `examples/` folders contain only `.gitkeep` files. For an open-source project, **the "git clone → example running in 60 seconds" experience** is decisive for adoption. Without it, the project will struggle to attract contributors.

### 3.4 ⚠️ `core/models/` ↔ `contracts/` coupling to clarify
[core/models/](../../src/modular_rag/core/models/) contains `document, chunk, query, retrieved, answer, trace, policy, metrics`. This is very close to what should be referenced by [contracts/](../../src/modular_rag/contracts/). An explicit ADR (ADR-0004?) on the core/contracts boundary would prevent circular coupling later.

### 3.5 ⚠️ `app/` vs `orchestration/` — ambiguous boundary
[app/](../../src/modular_rag/app/) (bootstrap, container, settings, lifecycle) and [orchestration/](../../src/modular_rag/orchestration/) (engine, registry, router, flow_compiler, state_machine) overlap conceptually. Without documentation, a contributor will not know what goes where. To be clarified in an ADR or in `docs/architecture/module-model.md` (currently empty).

### 3.6 ⚠️ Mention of `pscode.lioncloud.net` in an "open-source" project
The README announces "open-source" but the badges and the clone URL point to a private GitLab instance (Publicis). Either the project is **internal** (and "open-source" is misleading), or public mirroring must be planned. To be decided quickly — it impacts the license, the CI, and the issue templates.

### 3.7 ⚠️ No trace of the multimodal aspect in `src/`
V5 multimodal is mentioned in the roadmap and has its preset, but there is no `multimodal/`, `vision/`, `tables/`, or `audio/` module under `src/modular_rag/`. This is not necessarily a problem (you will add it in V5), but it should be explicitly called out as "deferred" in an ADR to avoid confusion.

### 3.8 ⚠️ The technical specification's `safety plane` is not visible
The technical specification mentions 6 planes: control / ingestion / knowledge / reasoning / **safety** / evaluation. The repository has [security/](../../src/modular_rag/security/) (detectors, filters, policies, redaction) but no explicit separation between `safety` (anti-prompt-injection, anti-poisoning) and `security` (RBAC, ACL). For V4 governance, these two concerns are distinct and might deserve two modules.

---

## 4. README review (before the rework)

### Strengths
- **Clear vision** ("context OS for RAG and agentic systems") — a good hook.
- **Mermaid V1→V5**: pedagogical and concise.
- **Standard sections** present (Table of Contents, Architecture, Getting started, Roadmap, Contributing, License).
- **Readable feature bullets**.

### Weaknesses (resolved on 2026-05-20)
- ✅ **Tense problem**: everything in the present tense while nothing exists → pre-alpha notice added.
- ✅ **No status badge** → `status: pre-alpha` badge added.
- ✅ **Mock code example** without a warning → marked `# Roadmap snippet — not functional yet`.
- ✅ **License "MIT (or another license to be defined)"** → settled on Apache 2.0.
- ✅ **No "Why this framework?"** → section added with a LangChain/LlamaIndex/Haystack comparison.
- ✅ **No link to the detailed vision** → link to `docs/architecture/overview.md` added.
- ⚠️ **French/English mix in the project** (README in English, but technical specification in French) — to be harmonized or offered bilingually. *Not yet resolved.*

---

## 5. Prioritized recommendations

### P0 (before inviting the 1st contributor)
1. ✅ **Add a "status pre-alpha" notice** at the top of the README. *(Done on 2026-05-20.)*
2. ⬜ **Fill in `pyproject.toml`** at minimum (name, version 0.0.0, python_requires, empty dependencies).
3. ✅ **Settle the license** (Apache 2.0 chosen, to be applied in the `LICENSE` file). *(Decided on 2026-05-20; `LICENSE` file to be updated separately.)*
4. ⬜ **Clarify "open-source vs internal Publicis"**: if private, remove "open-source" from the README; if public, plan a GitHub mirror.

### P1 (the first 2 weeks)
5. ⬜ **Write at least 3 completed ADRs**: `0001-modular-architecture`, `0002-contracts-and-plugins`, `0003-security-and-governance`.
6. ⬜ **Implement 1 end-to-end example** (`examples/simple_qa/`) that actually runs, even with a mocked LLM. It is adoption criterion #1.
7. ⬜ **Define and document the `contracts/`** (at least `retrieval.py`, `generation.py`, `chunking.py`) — they freeze the contractual interface; everything else follows from them.
8. ⬜ **Move the technical specification** into `docs/architecture/overview.md` (currently empty).

### P2 (before the first release)
9. ⬜ **Mirror `tests/` onto `src/`** (create `tests/unit/contracts/test_retrieval.py` etc.).
10. ✅ **Add a "Why?" / comparison** to the README (LlamaIndex vs LangChain vs this). *(Done on 2026-05-20.)*
11. ⬜ **Minimal CI** (`.gitlab-ci.yml` or GitHub Actions): lint + empty contract tests + doc build.
12. ⬜ **Settle the `app/` ↔ `orchestration/` boundary** in an ADR.

---

## 6. Conclusion

> *The structure is exceptionally well thought out for a modular RAG project — one of the most mature skeletons you could see at this stage (contracts/adapters separation, per-environment manifests, ADRs, contract tests, granular agents). But the README described a product that did not yet exist. **The gap between the documented ambition and the delivered code is today the project's biggest risk** — not the architecture, which is sound.*

> *Absolute priority: get **a single** V1 path working end-to-end (`simple_qa`), even minimal, before expanding. Otherwise, you risk building 5 versions of the API on paper without ever validating the V1 API through real usage.*

---

## 7. `README.md` rework (applied on 2026-05-20)

The README rework has been applied. It:

- honestly declares the **pre-alpha** status right at the top,
- adds a "Why this framework?" and a positioning vs LangChain / LlamaIndex / Haystack,
- moves the code examples behind a warning (`# Roadmap snippet — not functional yet`),
- adds a link to the technical specification (to be moved into `docs/architecture/overview.md`),
- settles the license on **Apache 2.0** (article 3 = explicit patent clause, essential for multi-employer enterprise use; the de facto standard for modern AI/ML frameworks: LangChain, LlamaIndex, Haystack, vLLM, transformers).
- keeps the existing sections (V1→V5 mermaid architecture, roadmap, contributing).

File modified: [README.md](../../README.md)

---

## 8. Follow-ups

- ⚠️ Update the [LICENSE](../../LICENSE) file with the official Apache 2.0 text (otherwise the README badge is dishonest).
- ⚠️ Settle the "open-source" mention vs private GitLab (point 3.6).
- ⬜ Remaining P0/P1/P2 items above.

---

## Critical files cited

- README: [README.md](../../README.md) *(reworked on 2026-05-20)*
- To fill in first: [pyproject.toml](../../pyproject.toml), [ROADMAP.md](../../ROADMAP.md), [CHANGELOG.md](../../CHANGELOG.md), [docs/architecture/overview.md](../architecture/overview.md)
- ADRs to write: [docs/adr/0001-modular-architecture.md](../adr/0001-modular-architecture.md), [docs/adr/0002-contracts-and-plugins.md](../adr/0002-contracts-and-plugins.md), [docs/adr/0003-security-and-governance.md](../adr/0003-security-and-governance.md)
- Contracts to define first: [src/modular_rag/contracts/retrieval.py](../../src/modular_rag/contracts/retrieval.py), [generation.py](../../src/modular_rag/contracts/generation.py), [chunking.py](../../src/modular_rag/contracts/chunking.py)
- Example to bring to life: [examples/simple_qa/](../../examples/simple_qa/)
