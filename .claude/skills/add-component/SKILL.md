---
name: add-component
description: Scaffold a new V1 component (chunker, retriever, generator, metric, embedder, vectorstore adapter) with implementation, unit test, contract test, and registry hints
---

# Add Component

Generic scaffolding workflow for any new V1 component. For retrievers, generators, or security guards specifically, prefer the more detailed `add-retriever`, `add-generator`, or `add-security-guard` skills — use this one for chunkers, metrics, embedders, or vectorstore adapters, or as a fallback.

**State of the art first:** before making design choices, read the matching digest in [docs/research/](../../../docs/research/) (DIGEST-chunking, DIGEST-evaluation, DIGEST-security, DIGEST-overviews, DIGEST-architecture) and cite the arXiv id backing each parameter. If a choice contradicts the digest, justify it explicitly in the MR.

## Steps

1. **Confirm the Protocol exists.** Check `src/modular_rag/contracts/` for the relevant Protocol (e.g. `Chunker`, `MetricsProtocol`, `Embedder`, `VectorStore`). If it doesn't exist yet, stop and ask — contracts are `ask`-tier in `.claude/settings.json` and CLAUDE.md rule 05.1 requires Protocol-first development.

2. **Implement.** Create the concrete class in the matching domain module (`ingestion/`, `eval/`) or adapter folder (`adapters/embeddings/`, `adapters/vectorstores/`), following an existing sibling implementation's structure and naming. Heavy external libraries must be lazily imported inside methods (CLAUDE.md rule 05.7).

3. **Unit test.** Add `tests/unit/<mirrored_path>/test_<component>.py`, mirroring `src/` structure (CLAUDE.md rule 04.4).

4. **Contract test.** Add `tests/contract/test_<component>_conformance.py` asserting `isinstance(instance, <Protocol>)` and exercising the Protocol's required methods.

5. **Register.** Add a factory entry in `src/modular_rag/orchestration/_default_factories.py`. Never instantiate the component directly anywhere else (CLAUDE.md rule 05.3).

6. **Wire into a manifest.** Reference the new component by name in a YAML under `manifests/presets/` (or a new preset) so it's actually reachable end-to-end.

7. **Validate.** Run the `quick-check` skill after step 2, then `full-check` after steps 3-5.

## Output

List the files created/modified with a one-line purpose for each, then run `full-check`.
