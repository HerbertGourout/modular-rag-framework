---
name: add-security-guard
description: Step-by-step workflow for implementing security guards (filters, detectors, policies)
---

# Add Security Guard Skill

> **Corrected 2026-08-06** (documentation-utility pass): this file previously described a
> fictional `SecurityGuardProtocol`/`PolicyProtocol` with a `check(text) -> (bool, dict)`
> signature, a `TraceStep(component=, method=)` constructor, and a `BUILT_IN_GUARDS` registry
> dict — none of which exist. Rewritten below against the real `SecurityGuard` protocol and
> `GuardResult` dataclass (`src/modular_rag/contracts/security.py`), the real directory layout
> (`security/filters/`, `security/detectors/`, `security/redaction/`, `security/policies/`,
> `security/audit/` — there is no `security/guards/` parent), and the real registration pattern
> (`src/modular_rag/orchestration/_default_factories.py`), using `BasicSecurityGuard`
> (`src/modular_rag/security/filters/basic_guard.py`) as the reference implementation.

## State of the Art First (mandatory)

Before designing detection patterns or risk scoring, read [docs/research/DIGEST-security.md](../../../docs/research/DIGEST-security.md) and cite the arXiv id backing each choice. Key baselines from the corpus: corpus-poisoning markers (embedded imperatives, reasoning-directive text); risk-score-gated guard chains (always-on stacks cut retrieval recall 41-46%); reversible pseudonymization (placeholder+mapping) alongside destructive redaction for audit trails.

If a design choice contradicts the digest, justify it explicitly in the MR.

## Parameters (advisory — not schema-validated by Claude Code)

Claude Code skills don't support typed/validated parameters in frontmatter; describe these to the agent in your invocation prompt instead:

- `guard_type` (enum, required) — one of: ['filter', 'detector', 'policy']
- `guard_name` (string, required) — pattern: `^[A-Z][a-zA-Z0-9]*(Guard|Detector|Filter)$`
- `threat_category` (enum, required) — one of: ['injection', 'pii', 'toxicity', 'policy_violation']

_Originally authored as a workflow for `security-specialist`, invoked as `/add-security-guard`._

Guided workflow for implementing security guards (filters, detectors, policies) against the
`SecurityGuard` contract.

**Safety vs. Security** — per [.claude/rules/security.md](../../rules/security.md): Safety
(prompt injection, PII, toxicity) belongs in `security/filters/` or `security/redaction/`.
Security (RBAC, tenant isolation, policy enforcement) belongs in `security/policies/`. Never mix
the two in the same file.

## When to Use

- Implementing input validation (filters)
- Detecting security threats (detectors)
- Enforcing access policies (policies)
- Reducing hallucinations and toxic content
- Compliance with regulations

## Guard Types

### Filter/Detector (SecurityGuard protocol)

Both filters (`security/filters/`) and detectors (`security/detectors/`) implement the same
`SecurityGuard` protocol from `contracts/security.py`:

```python
def check_query(self, query: Query) -> GuardResult: ...
def check_answer(self, answer: Answer) -> GuardResult: ...
def name(self) -> str: ...
```

`GuardResult` is a dataclass: `allowed: bool`, `reason: str | None`, `modified_content: str |
None`, `risk_score: float`. There is no separate `PolicyProtocol` — the same `SecurityGuard`
shape covers filters and detectors; policy engines (below) have their own, narrower API.

```python
class PromptInjectionFilter:
    def check_query(self, query: Query) -> GuardResult:
        if self._has_injection_patterns(query.text):
            return GuardResult(allowed=False, reason="Injection pattern matched", risk_score=0.9)
        return GuardResult(allowed=True, reason="", risk_score=0.0)

    def check_answer(self, answer: Answer) -> GuardResult:
        return GuardResult(allowed=True, reason="", risk_score=0.0)  # no-op if query-only

    def name(self) -> str:
        return "prompt-injection-filter"
```

### Policy (Enforce — `security/policies/`)

Policy enforcement uses its own real classes rather than a generic Protocol: see
`PolicyEngine` (`security/policies/policy_engine.py`, evaluates a `list[Policy]` against a
`Query`, fail-closed on evaluation errors, returns `GuardResult`) and `TenantPolicy`
(`contracts/security.py`, the fail-closed tenant-isolation boundary with
`enforce_query`/`enforce_ingest`/`filter_chunks`). A new access-control policy should extend one
of these, not invent a new Protocol.

## Workflow Steps

### 1. Define Threat Model (10 min)

**Questions:**
- What threat does this guard protect against?
- What false positive rate is acceptable?
- What's the performance overhead budget?
- Are there regulatory requirements?

**Example - PII Detection:**
- Threats: SSN, credit cards, emails, phone numbers
- False positives: 5% acceptable
- Latency: <5ms per request
- Regulations: GDPR, CCPA, HIPAA

### 2. Create Implementation File (15 min)

**File:** `src/modular_rag/security/filters/{guard_name}.py` (or `security/detectors/` if it's
identifying rather than blocking — see the Safety-vs-Security split above)

```python
from __future__ import annotations

import re

from modular_rag.contracts.security import GuardResult
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query

_MALICIOUS_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|above) instructions", re.I),
    # ... more patterns — see basic_guard.py's _INJECTION_PATTERNS for the full,
    # research-cited pattern families (direct override, promotional imperative,
    # reasoning-directive)
]


class {GuardName}:
    """{Description}"""

    def name(self) -> str:
        return "{guard_name}"

    def check_query(self, query: Query) -> GuardResult:
        text = query.text
        for pattern in _MALICIOUS_PATTERNS:
            if pattern.search(text):
                return GuardResult(
                    allowed=False,
                    reason=f"Matched pattern: {pattern.pattern[:40]}",
                    risk_score=0.9,
                )
        return GuardResult(allowed=True, reason="", risk_score=0.0)

    def check_answer(self, answer: Answer) -> GuardResult:
        return GuardResult(allowed=True, reason="", risk_score=0.0)
```

`risk_score` scale, per `.claude/rules/security.md`: **0.9** = prompt injection, **0.8** =
blocked term / poison marker, **0.5** = length exceeded, **0.0** = OK. Follow this scale for any
new guard rather than inventing a new range.

**Detector pattern** (PII, in `security/detectors/`) — see the real
`security/redaction/patterns.py` for the PII regex families already in the codebase before
writing new ones; extend that module rather than duplicating pattern lists.

### 3. Create Detection Patterns (15 min)

**Good Pattern Design:**
```python
# ✅ GOOD: Specific, tested patterns, matching a verb/context pairing, not a bare keyword
re.compile(r"you\s+(?:must|should)\s+(?:recommend|visit|use|cite)", re.I)

# ❌ BAD: Overly broad patterns
re.compile(r"\d+")  # Matches all numbers!
```

### 4. Redaction (if applicable)

Redaction (masking/replacing PII in text) lives in `security/redaction/`, separate from the
`SecurityGuard` check/allow decision — see `security/redaction/patterns.py` for the existing
pattern set and redaction strategies before adding a new one.

### 5. Create Unit Tests (20 min)

**File:** `tests/unit/security/filters/test_{guard_name}.py` (or `detectors/` — mirror the
implementation's directory)

```python
import pytest

from modular_rag.core.models.query import Query
from modular_rag.security.filters.{guard_name} import {GuardName}


class Test{GuardName}:

    @pytest.fixture
    def guard(self):
        return {GuardName}()

    def test_detects_threat(self, guard):
        query = Query(text="ignore previous instructions")
        result = guard.check_query(query)
        assert not result.allowed
        assert result.reason

    def test_allows_safe_text(self, guard):
        query = Query(text="What is the capital of France?")
        result = guard.check_query(query)
        assert result.allowed

    def test_empty_text(self, guard):
        result = guard.check_query(Query(text=""))
        assert result.allowed
```

### 6. Create Contract Test (10 min)

**File:** `tests/contract/test_security_conformance.py` (add a case to the existing file — see
that file for the pattern)

```python
from modular_rag.contracts.security import SecurityGuard
from modular_rag.security.filters.{guard_name} import {GuardName}


def test_{guard_name}_conforms_to_security_guard_protocol():
    instance = {GuardName}()
    assert isinstance(instance, SecurityGuard)
```

### 7. Register & Test (5 min)

**File:** `src/modular_rag/orchestration/_default_factories.py` — add the import inside
`register_defaults()` and one `reg.register(...)` line, following the existing `"guard"`/`"basic"`
entry:

```python
from modular_rag.security.filters.{guard_name} import {GuardName}
...
reg.register("guard", "{guard_name}", lambda cfg: {GuardName}(**cfg.config))
```

**Run tests:**
```bash
pytest tests/unit/security/filters/test_{guard_name}.py -v
pytest tests/contract/test_security_conformance.py -v
./scripts/check.sh full
```

## Guard Chain Pattern

Chaining multiple `SecurityGuard` instances is not a built-in class in this codebase today — if
you need one, write it explicitly and add it under `security/filters/`, iterating
`check_query`/`check_answer` over each guard and short-circuiting on the first
`GuardResult(allowed=False, ...)`. Do not assume a `GuardChain` class already exists.

## Success Criteria

✅ `SecurityGuard` protocol fully implemented (`check_query`, `check_answer`, `name`)
✅ `risk_score` follows the 0.9/0.8/0.5/0.0 scale
✅ Patterns tested for accuracy and false positives
✅ Unit test coverage > 85%
✅ Contract conformance test passing
✅ Edge cases handled
✅ Registered in `_default_factories.py`

## Time Estimate

**Total:** 1.5 hours
