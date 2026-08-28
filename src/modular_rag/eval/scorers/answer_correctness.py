"""Answer-correctness scorer (Batch 13, external plan — "Offline benchmark").

Correctness = response <-> gold-answer alignment, the third pairwise
generation target in docs/research/DIGEST-evaluation.md #1 ([2504.14891]),
distinct from `eval/scorers/exact_match.py::ExactMatchEvaluator`'s
`answer_relevance` (bag-of-words token-set F1 — order- and phrasing-
insensitive). `SequenceMatcher.ratio()` is sensitive to token *order* and
contiguous phrasing, so it catches a case token-F1 cannot: an answer using
exactly the gold answer's words in a different order (e.g. a reworded
negation) scores high on token-F1 but low here, and vice versa for near-
verbatim phrasing with one substituted word. Deterministic and dependency-
free (Python's own `difflib`, no embeddings/LLM call) to keep the benchmark
reproducible with no network access (ADR-0008).
"""
from __future__ import annotations

from difflib import SequenceMatcher

from modular_rag.core.models.metrics import Metrics


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def answer_correctness_score(answer_text: str, gold_text: str) -> float:
    """`SequenceMatcher.ratio()` on normalized (lowercased, whitespace-
    collapsed) text — `1.0` for identical text, `0.0` for two empty strings
    compared against each other counts as a degenerate match (`ratio()`
    itself returns `1.0` for two empty sequences); an empty gold answer
    should never occur in a well-formed golden set (`BenchmarkCase.
    expected_answer` is a required field), so this is not special-cased
    further.
    """
    return SequenceMatcher(None, _normalize(answer_text), _normalize(gold_text)).ratio()


def compute_answer_correctness(answer_text: str, gold_text: str) -> Metrics:
    return Metrics(answer_correctness=answer_correctness_score(answer_text, gold_text))
