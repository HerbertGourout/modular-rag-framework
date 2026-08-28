"""Faithfulness scorer (Batch 13, external plan — "Offline benchmark").

Faithfulness = response <-> retrieved-context alignment, one of the three
pairwise generation targets in docs/research/DIGEST-evaluation.md #1
([2504.14891]: Relevance / Faithfulness / Correctness). The digest's own
"LLM-as-judge" section (RAGAS/ARES/TRACe) is explicitly the higher-fidelity
option, but an LLM judge is non-deterministic and needs a paid API call --
exactly what this benchmark must avoid to stay reproducible in CI with no
LLM key (ADR-0008, this task's own "reproducible benchmark" acceptance
criterion). This module is therefore a deterministic, lexical-overlap
*proxy* for faithfulness, not the LLM-judge metric the digest describes --
documented honestly as a proxy (matching this codebase's existing style,
e.g. `docs/observability/slo.md`'s "retrieval quality (proxy)" section) so a
reader does not mistake it for the real thing.
"""
from __future__ import annotations

import re

from modular_rag.core.models.metrics import Metrics

_TOKEN_PATTERN = re.compile(r"\w+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


def faithfulness_score(answer_text: str, context_passages: list[str]) -> float:
    """Fraction of the answer's distinct content tokens that also appear
    somewhere in the retrieved context — "how much of what the answer claims
    can be traced back to a retrieved passage." An answer with no tokens (or
    a benchmark case with no context at all) scores `0.0`: a refusal or
    empty answer over empty context has nothing to be faithful *to*, and
    scoring it `1.0` (vacuously "fully faithful") would hide the fact that
    the case produced no groundable content, exactly the failure mode this
    metric exists to surface.
    """
    answer_tokens = _tokenize(answer_text)
    if not answer_tokens:
        return 0.0
    context_tokens: set[str] = set()
    for passage in context_passages:
        context_tokens |= _tokenize(passage)
    if not context_tokens:
        return 0.0
    return len(answer_tokens & context_tokens) / len(answer_tokens)


def compute_faithfulness(answer_text: str, context_passages: list[str]) -> Metrics:
    return Metrics(faithfulness=faithfulness_score(answer_text, context_passages))
