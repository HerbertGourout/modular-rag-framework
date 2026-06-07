"""Contract conformance tests for SecurityGuard and Redactor implementations."""
from __future__ import annotations

import pytest

from modular_rag.contracts.security import GuardResult, Redactor, SecurityGuard
from modular_rag.core.ids import new_id
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query
from modular_rag.security.filters.basic_guard import BasicSecurityGuard
from modular_rag.security.redaction.patterns import PatternRedactor


GUARDS = [BasicSecurityGuard()]
REDACTORS = [PatternRedactor()]


@pytest.mark.parametrize("guard", GUARDS, ids=lambda g: g.name())
def test_implements_security_guard_protocol(guard):
    assert isinstance(guard, SecurityGuard)


@pytest.mark.parametrize("guard", GUARDS, ids=lambda g: g.name())
def test_check_query_returns_guard_result(guard):
    q = Query(text="What is the weather today?")
    result = guard.check_query(q)
    assert isinstance(result, GuardResult)
    assert isinstance(result.allowed, bool)
    assert isinstance(result.reason, str)
    assert 0.0 <= result.risk_score <= 1.0


@pytest.mark.parametrize("guard", GUARDS, ids=lambda g: g.name())
def test_check_answer_returns_guard_result(guard):
    a = Answer(query_id=new_id(), text="The answer is 42.")
    result = guard.check_answer(a)
    assert isinstance(result, GuardResult)


@pytest.mark.parametrize("redactor", REDACTORS, ids=lambda r: r.name())
def test_implements_redactor_protocol(redactor):
    assert isinstance(redactor, Redactor)


@pytest.mark.parametrize("redactor", REDACTORS, ids=lambda r: r.name())
def test_redact_returns_string(redactor):
    result = redactor.redact("Hello world")
    assert isinstance(result, str)


@pytest.mark.parametrize("redactor", REDACTORS, ids=lambda r: r.name())
def test_redact_benign_text_unchanged(redactor):
    text = "The quick brown fox jumps over the lazy dog."
    assert redactor.redact(text) == text
