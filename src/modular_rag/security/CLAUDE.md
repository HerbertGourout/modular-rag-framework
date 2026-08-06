# CLAUDE.md — Security Module

This file provides security-specific guidance for Claude working on the security module. Read this **before editing any file in this directory**.

---

## ⚠️ Safety Critical Module

The security module handles **sensitive data** (PII, credentials, policy enforcement). Claude must be extremely careful about:
- Exposing secrets in logs or error messages
- Creating overly permissive regex patterns (PII detection bypass)
- Mixing Safety (filters, redaction) with Security (policies, RBAC)
- Importing from domain modules (FORBIDDEN)

---

## 1. No Cross-Domain Imports

### Rule: Never Import from Domain Modules
The security module sits **above** domain modules in the architecture. It cannot import from `ingestion/`, `retrieval/`, `generation/`, `agents/`, `memory/`, or `eval/`.

### ❌ FORBIDDEN
```python
# ❌ Security importing from domain module
from modular_rag.retrieval.bm25 import BM25Retriever
from modular_rag.generation.openai import OpenAIGenerator

# This breaks hexagonal layering!
```

### ✅ ALLOWED
```python
# ✅ Security imports from contracts and core
from modular_rag.contracts.security import SecurityGuard, PolicyEngine
from modular_rag.core.models import Document, Query
from modular_rag.core.errors import SecurityError
```

**Why this matters**: Security is foundational. Domain modules depend on security. If security depended on domain modules, it would create circular dependencies.

---

## 2. Safety vs Security (Distinct Concerns)

### Safety (Filters, Redaction)
**Purpose**: Protect against content issues (prompt injection, PII, toxicity).

**Location**: `security/filters/`, `security/redaction/`

**Example**:
```python
# safety/ concern: block injection attempts
class PromptGuard:
    def evaluate(self, query: Query) -> bool:
        if "'; DROP TABLE" in query.text:
            return False  # Block SQL injection
        return True

# safety/ concern: redact PII
class PatternRedactor:
    def redact(self, text: str) -> str:
        return re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)  # Mask SSNs
```

### Security (Policies, RBAC)
**Purpose**: Enforce access control, audit, compliance.

**Location**: `security/policies/`

**Example**:
```python
# security/ concern: enforce role-based access
class RBACPolicy:
    def can_access(self, user: User, resource: Resource) -> bool:
        if user.role == "admin":
            return True
        if user.role == "user" and resource.visibility == "public":
            return True
        return False

# security/ concern: audit log
class AuditLog:
    def log_access(self, user: User, action: str, resource: Resource):
        logger.info(f"User {user.id} {action} {resource.id}")
```

### ❌ Bad: Mixing Concerns
```python
# ❌ Bad: mixing Safety and Security
class MixedGuard:
    def evaluate(self, query: Query, user: User):
        # This is confusing: is this Safety or Security?
        if self._is_prompt_injection(query):  # Safety
            return False
        if user.role != "user":  # Security
            return False
        return True
```

### ✅ Good: Separate Concerns
```python
# ✅ Good: distinct Safety and Security
class PromptGuard:  # Safety
    def evaluate(self, query: Query) -> bool:
        return not self._is_prompt_injection(query)

class AccessPolicy:  # Security
    def can_execute(self, user: User) -> bool:
        return user.role in ["admin", "user"]
```

---

## 3. PII Detection & Redaction Rules

### Never Log Full Text
Full text may contain PII (names, emails, SSNs, credit cards, medical info).

### ❌ WRONG
```python
def evaluate(self, query: Query) -> bool:
    logger.info(f"Evaluating query: {query.text}")  # ❌ May expose PII!
    # ... rest of logic
```

### ✅ CORRECT
```python
def evaluate(self, query: Query) -> bool:
    logger.info(f"Evaluating query (length={len(query.text)})")  # ✅ Safe
    # ... rest of logic
```

### PII Patterns to Detect
Use `PatternRedactor` to mask:
- **SSN**: `\b\d{3}-\d{2}-\d{4}\b` → `[SSN]`
- **Credit Card**: `\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b` → `[CC]`
- **Email**: `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b` → `[EMAIL]`
- **Phone**: `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b` → `[PHONE]`
- **Medical**: `ICD-10|\bmedication\b|\bdiagnosis\b` → `[MEDICAL]`

**Reference**: See [src/modular_rag/security/redaction/pattern_redactor.py](../redaction/pattern_redactor.py) for implementation.

---

## 4. Risk Scoring Guidelines

### TraceStep Metadata: risk_score Field
Every guard evaluation must emit a `risk_score` (0.0 to 1.0) in metadata.

### Scale
```
1.0 = Critical (block immediately)
0.9 = High (prompt injection detected)
0.8 = Medium (suspicious term found)
0.5 = Low (threshold exceeded)
0.0 = Safe (pass through)
```

### ✅ Example
```python
def evaluate(self, query: Query) -> GuardResult:
    trace = Trace()
    
    # Check for injection
    if self._is_injection(query):
        trace.add_step(TraceStep(
            name="guard_injection_check",
            metadata={"risk_score": 0.9}
        ))
        return GuardResult(is_safe=False, risk_score=0.9)
    
    # Check for PII
    pii_count = self._count_pii(query)
    if pii_count > 0:
        trace.add_step(TraceStep(
            name="guard_pii_check",
            metadata={"risk_score": 0.5 + (0.1 * pii_count)}
        ))
        return GuardResult(is_safe=False, risk_score=min(0.8, 0.5 + (0.1 * pii_count)))
    
    # Safe
    trace.add_step(TraceStep(
        name="guard_all_checks",
        metadata={"risk_score": 0.0}
    ))
    return GuardResult(is_safe=True, risk_score=0.0)
```

---

## 5. Never Hardcode Security Thresholds

### ❌ WRONG: Hardcoded Values
```python
class PromptGuard:
    def evaluate(self, query: Query) -> bool:
        # ❌ Hardcoded threshold
        if len(query.text) > 1000:  # Why 1000? No flexibility!
            return False
        return True
```

### ✅ CORRECT: Configurable via Manifest
```python
class PromptGuard:
    def __init__(self, max_query_length: int = 1000):
        self.max_query_length = max_query_length
    
    def evaluate(self, query: Query) -> bool:
        if len(query.text) > self.max_query_length:
            return False
        return True

# In orchestration/registry.py:
@_register_factory("PromptGuard", SecurityGuard)
def create_prompt_guard(config: dict) -> SecurityGuard:
    return PromptGuard(
        max_query_length=config.get("max_query_length", 1000)
    )

# In manifest YAML:
components:
  guard:
    type: "PromptGuard"
    config:
      max_query_length: 2000
```

---

## 6. Testing Security Components

### Unit Tests (No External Services)
```python
# tests/unit/security/test_prompt_guard.py

def test_guard_blocks_sql_injection():
    guard = PromptGuard()
    query = Query(text="'; DROP TABLE users; --")
    result = guard.evaluate(query)
    assert result.is_safe is False
    assert result.risk_score >= 0.9

def test_guard_allows_safe_query():
    guard = PromptGuard()
    query = Query(text="What is machine learning?")
    result = guard.evaluate(query)
    assert result.is_safe is True
    assert result.risk_score == 0.0
```

### Conformance Tests (All Implementations)
```python
# tests/contract/test_security_conformance.py

import pytest
from modular_rag.contracts.security import SecurityGuard
from modular_rag.security.filters import PromptGuard, ToxicityFilter

@pytest.mark.parametrize("guard_class", [PromptGuard, ToxicityFilter])
def test_security_guard_implements_protocol(guard_class):
    """Verify all SecurityGuard implementations conform to Protocol."""
    guard = guard_class()
    assert isinstance(guard, SecurityGuard)
    
    # Test interface
    query = Query(text="test")
    result = guard.evaluate(query)
    assert hasattr(result, "is_safe")
    assert hasattr(result, "risk_score")
    assert 0.0 <= result.risk_score <= 1.0
```

---

## 7. Vault/Credentials: Never Log or Expose

### ❌ WRONG
```python
# ❌ Never log credentials
api_key = os.getenv("MRAG_SECURITY_API_KEY")
logger.info(f"Using API key: {api_key}")  # ❌ Exposed!
```

### ✅ CORRECT
```python
# ✅ Safe: just log that we loaded a key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SecurityError("OPENAI_API_KEY not set")
logger.info("Loaded API key from environment")  # ✅ Safe
```

### Environment Variables (Corrected 2026-08-06)

There is no `MRAG_SECURITY_API_KEY`/`MRAG_AUTH_SECRET`/`MRAG_*` convention in this codebase —
those don't exist anywhere in `src/`. The only credential env vars anything actually reads are
the LLM SDKs' own standard names:
```bash
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```
(`app/settings.py` declares a separate `MRAG_`-prefixed `Settings` class, but it's orphaned —
nothing in the real pipeline-wiring path ever constructs it.)

---

## 8. Summary: Security Module Dos & Don'ts

### ✅ DO
- Import from `contracts/security.py` and `core/models/`
- Separate Safety (filters, redaction) from Security (policies, RBAC)
- Emit TraceStep with risk_score in metadata
- Use lazy imports for heavy deps (never at module level)
- Configure via manifest YAML (no hardcoded thresholds)
- Test with unit + conformance tests
- Load credentials from environment variables
- Log safely (never log full text or secrets)
- Use PatternRedactor for PII masking

### ❌ NEVER
- Import from domain modules (`ingestion/`, `retrieval/`, etc.)
- Mix Safety and Security in one class
- Log full query text (might contain PII)
- Hardcode security thresholds or credentials
- Create overly permissive regex patterns
- Leave unmasked PII in logs or traces
- Implement a guard without conformance test
- Modify protocols without updating tests

---

## 9. Common Violations & Fixes

### Violation 1: Cross-Domain Import
```python
# ❌ Bad
from modular_rag.retrieval.bm25 import BM25Retriever

# ✅ Fix
from modular_rag.contracts.retrieval import Retriever
```

### Violation 2: Mixing Safety & Security
```python
# ❌ Bad
class GuardAndPolicy:
    def evaluate(self, query, user):
        # Both safety and security — confusing!
        return self._is_safe(query) and self._can_access(user)

# ✅ Fix
class PromptGuard:  # Safety
    def evaluate(self, query) -> bool:
        return self._is_safe(query)

class AccessPolicy:  # Security
    def can_access(self, user) -> bool:
        return user.role in ["admin", "user"]
```

### Violation 3: Logging PII
```python
# ❌ Bad
logger.info(f"Processing query: {query.text}")

# ✅ Fix
logger.info(f"Processing query (len={len(query.text)})")
```

---

## References

- [.claude/rules/security.md](../../.claude/rules/security.md) — Global security rules
- [src/modular_rag/contracts/security.py](../contracts/security.py) — SecurityGuard Protocol
- [src/modular_rag/security/](../security/) — Security module structure
- [ADR-0003: Security & Governance](../../docs/adr/0003-security-and-governance.md) — Architecture decision

---

**Work safely. Protect user data. Never compromise on security.**
