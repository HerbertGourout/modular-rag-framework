---
name: validate-security
description: Verify security-sensitive changes respect the 7-layer defense rules (no hardcoded secrets, no cross-domain imports, no direct wiring, lazy imports, PII patterns) before merging
---

# Validate Security

Manual checklist for security-sensitive changes. There is no single CI job for this (the `futureHooks` entries in `.claude/settings.json`'s history reference `scripts/validate_imports.py` etc., but those scripts don't exist yet — this skill runs the equivalent checks by hand with grep/ruff).

## What to do, in order

**1. No hardcoded secrets**
```bash
grep -rniE '(api[_-]?key|secret|password|token)\s*=\s*["\047][^"\047]+["\047]' src/modular_rag/ --include="*.py" | grep -v "os.getenv\|os.environ"
```
Anything returned here that isn't reading from `os.getenv()`/`os.environ` is a violation — see CLAUDE.md block 07 / `.claude/rules/security-layers.md` Layer 05.

**2. No cross-domain imports** (CLAUDE.md block 02 — domain modules import only `contracts/` + `core/models/`, never each other)
```bash
for d in ingestion retrieval generation security agents memory eval; do
  echo "--- $d ---"
  grep -rn "from modular_rag\.\(ingestion\|retrieval\|generation\|security\|agents\|memory\|eval\)" src/modular_rag/$d/ \
    | grep -v "from modular_rag\.$d"
done
```
Any match means domain `$d` imports from a sibling domain — forbidden.

**3. No direct component wiring** (CLAUDE.md block 05 rule 3 — components are wired only via `orchestration/registry.py` + manifest YAML)
```bash
grep -rn "= [A-Z][A-Za-z]*\(Retriever\|Generator\|Chunker\|Embedder\)(" src/modular_rag/ --include="*.py" | grep -v "orchestration/\|tests/"
```
Direct instantiation of a concrete component outside `orchestration/` or `tests/` is a violation.

**4. Lazy imports on heavy dependencies** (CLAUDE.md block 05 rule 7)
```bash
grep -rn "^import \(qdrant_client\|rank_bm25\|sentence_transformers\|openai\|anthropic\|fitz\)" src/modular_rag/ --include="*.py"
grep -rn "^from \(qdrant_client\|rank_bm25\|sentence_transformers\|openai\|anthropic\|fitz\)" src/modular_rag/ --include="*.py"
```
Any match is a module-level import of a heavy dependency — must be moved inside the method that uses it.

**5. PII patterns** — read `src/modular_rag/security/` redaction code by hand and confirm new/changed patterns are documented and tested in `tests/unit/security/`. This isn't automatable with grep; use the `security-specialist` subagent if unsure.

## Report format

For each of the 5 checks: ✅ clean / ❌ N violations found (list file:line). Don't mark the skill as passed if any check has unresolved violations.
