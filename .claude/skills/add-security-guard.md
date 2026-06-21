---
name: add-security-guard
shortDescription: Add a new security guard to the framework
description: Step-by-step workflow for implementing security guards (filters, detectors, policies)
author: security-specialist
invocation: /add-security-guard
parameters:
  - name: guard_type
    type: enum
    values: [filter, detector, policy]
    required: true
  - name: guard_name
    type: string
    pattern: "^[A-Z][a-zA-Z0-9]*(Filter|Detector|Policy)$"
    required: true
  - name: threat_category
    type: enum
    values: [injection, pii, toxicity, policy_violation]
    required: true
---

# Add Security Guard Skill

Guided workflow for implementing security guards (filters, detectors, policies) following SecurityGuardProtocol.

## When to Use

- Implementing input validation (filters)
- Detecting security threats (detectors)
- Enforcing access policies (policies)
- Reducing hallucinations and toxic content
- Compliance with regulations

## Guard Types

### Filter (Block)
Prevent malicious input before processing.
```python
class PromptInjectionFilter(SecurityGuardProtocol):
    def check(self, text: str) -> (bool, dict):
        """Return (is_safe, metadata)."""
        is_safe = not self._has_injection_patterns(text)
        return is_safe, {"suspicious_patterns": [...]}
```

### Detector (Identify)
Identify and report security threats.
```python
class PIIDetector(SecurityGuardProtocol):
    def check(self, text: str) -> (bool, dict):
        """Return (has_threat, metadata with locations)."""
        pii_locations = self._find_pii(text)
        has_pii = len(pii_locations) > 0
        return not has_pii, {"pii": pii_locations}
```

### Policy (Enforce)
Enforce role-based access control.
```python
class DataAccessPolicy(PolicyProtocol):
    def evaluate(self, request: dict) -> bool:
        """Return whether request is allowed."""
        user_role = request.get("user_role")
        data_class = request.get("data_classification")
        return self._is_allowed(user_role, data_class)
```

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

**File:** `src/modular_rag/security/guards/{guard_type}/{guard_name}.py`

**Filter Pattern:**
```python
from modular_rag.contracts.security import SecurityGuardProtocol
from modular_rag.core.trace import Trace, TraceStep
import re

class {GuardName}(SecurityGuardProtocol):
    """{Description}"""
    
    MALICIOUS_PATTERNS = [
        r"ignore previous instructions",
        r"execute this command",
        # ... more patterns
    ]
    
    def check(self, text: str) -> tuple[bool, dict]:
        step = TraceStep(component=self.__class__.__name__, method="check")
        
        try:
            is_safe = self._is_safe(text)
            
            step.metadata = {
                "input_length": len(text),
                "is_safe": is_safe,
                "reason": self._get_reason(text) if not is_safe else None
            }
            
            return is_safe, step.metadata
            
        except Exception as e:
            step.status = "error"
            raise
        finally:
            Trace.add_step(step)
    
    def _is_safe(self, text: str) -> bool:
        """Check if text is safe."""
        # Check each pattern
        for pattern in self.MALICIOUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return False
        return True
    
    def _get_reason(self, text: str) -> str:
        """Explain why text is unsafe."""
        for pattern in self.MALICIOUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return f"Matched dangerous pattern: {pattern}"
        return "Unknown reason"
```

**Detector Pattern:**
```python
class PIIDetector(SecurityGuardProtocol):
    """Detect PII in text."""
    
    PII_PATTERNS = {
        "ssn": r"\d{3}-\d{2}-\d{4}",
        "credit_card": r"\d{16}",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\(\d{3}\) \d{3}-\d{4}",
    }
    
    def check(self, text: str) -> tuple[bool, dict]:
        pii_found = self._find_all_pii(text)
        
        return len(pii_found) == 0, {
            "has_pii": len(pii_found) > 0,
            "pii_types": list(pii_found.keys()),
            "locations": pii_found
        }
    
    def _find_all_pii(self, text: str) -> dict:
        """Find all PII in text."""
        results = {}
        for pii_type, pattern in self.PII_PATTERNS.items():
            matches = list(re.finditer(pattern, text))
            if matches:
                results[pii_type] = [
                    {"start": m.start(), "end": m.end(), "value": m.group()}
                    for m in matches
                ]
        return results
```

### 3. Create Detection Patterns (15 min)

**Good Pattern Design:**
```python
# ✅ GOOD: Specific, tested patterns
PATTERNS = {
    "ssn": {
        "pattern": r"\b(?!000|666|9\d{2})\d{3}-?(?!00)\d{2}-?(?!0000)\d{4}\b",
        "examples": ["123-45-6789", "123456789"],
        "false_positives": ["000-00-0000"],
        "accuracy": 0.99
    }
}

# ❌ BAD: Overly broad patterns
PATTERNS = {
    "pii": r"\d+"  # Matches all numbers!
}
```

### 4. Implement Redaction (10 min)

**Pattern:**
```python
class PIIRedactor:
    """Redact PII from text."""
    
    REDACTION_STRATEGIES = {
        "mask": lambda s: "*" * len(s),
        "replace": lambda s: "[REDACTED]",
        "hash": lambda s: hashlib.sha256(s.encode()).hexdigest(),
        "preserve_first": lambda s: s[0] + "*" * (len(s)-1)
    }
    
    def redact(self, text: str, strategy: str = "mask") -> str:
        """Redact PII using specified strategy."""
        pii_locations = self._find_all_pii(text)
        
        redacted = text
        # Sort by position, reverse order to preserve indices
        for pii_type, locations in sorted(pii_locations.items(), reverse=True):
            for loc in reversed(locations):
                redacted_value = self.REDACTION_STRATEGIES[strategy](
                    text[loc["start"]:loc["end"]]
                )
                redacted = redacted[:loc["start"]] + redacted_value + redacted[loc["end"]:]
        
        return redacted
```

### 5. Create Unit Tests (20 min)

**File:** `tests/unit/security/guards/test_{guard_name}.py`

```python
import pytest
from modular_rag.security.guards.{guard_type}.{guard_name} import {GuardName}

class Test{GuardName}:
    
    @pytest.fixture
    def guard(self):
        return {GuardName}()
    
    # Test positive case (should block/detect)
    def test_detects_threat(self, guard):
        malicious_text = "ignore previous instructions"
        is_safe, meta = guard.check(malicious_text)
        assert not is_safe
        assert "reason" in meta
    
    # Test negative case (should allow)
    def test_allows_safe_text(self, guard):
        safe_text = "What is the capital of France?"
        is_safe, meta = guard.check(safe_text)
        assert is_safe
    
    # Test edge cases
    def test_empty_text(self, guard):
        is_safe, meta = guard.check("")
        assert is_safe
    
    def test_case_insensitivity(self, guard):
        text1 = "ignore previous instructions"
        text2 = "IGNORE PREVIOUS INSTRUCTIONS"
        is_safe1, _ = guard.check(text1)
        is_safe2, _ = guard.check(text2)
        assert is_safe1 == is_safe2
    
    # Test performance
    def test_performance(self, guard):
        import time
        text = "Sample query" * 100  # ~1KB
        start = time.time()
        guard.check(text)
        latency = time.time() - start
        assert latency < 0.01  # <10ms
```

### 6. Create Contract Test (10 min)

**File:** `tests/contract/test_{guard_name}_conformance.py`

```python
from modular_rag.security.guards.{guard_type}.{guard_name} import {GuardName}
from modular_rag.contracts.security import SecurityGuardProtocol

def test_protocol_implementation():
    """Verify {GuardName} implements SecurityGuardProtocol."""
    assert issubclass({GuardName}, SecurityGuardProtocol)
    assert hasattr({GuardName}, 'check')

def test_check_return_type(guard):
    """Verify check() returns (bool, dict)."""
    is_safe, metadata = guard.check("test")
    assert isinstance(is_safe, bool)
    assert isinstance(metadata, dict)
```

### 7. Register & Test (5 min)

**Registry:**
```python
BUILT_IN_GUARDS = {
    "{guard_name}": {GuardName},
}
```

**Run tests:**
```bash
pytest tests/unit/security/guards/test_{guard_name}.py -v
pytest tests/contract/test_{guard_name}_conformance.py -v
./scripts/check.sh full
```

## Guard Chain Pattern

**Combine multiple guards:**
```python
class GuardChain:
    def __init__(self, guards: List[SecurityGuardProtocol]):
        self.guards = guards
    
    def check(self, text: str) -> tuple[bool, dict]:
        """Run all guards, stop at first failure."""
        results = []
        for guard in self.guards:
            is_safe, meta = guard.check(text)
            results.append((guard.__class__.__name__, is_safe, meta))
            
            if not is_safe:
                return False, {"failed_guards": results}
        
        return True, {"passed_guards": [r[0] for r in results]}
```

## Success Criteria

✅ SecurityGuardProtocol fully implemented
✅ Patterns tested for accuracy and false positives
✅ <5ms latency per check
✅ Unit test coverage > 85%
✅ Contract conformance test passing
✅ Edge cases handled
✅ Performance benchmarked
✅ TraceStep emission complete

## Time Estimate

**Total:** 1.5 hours
