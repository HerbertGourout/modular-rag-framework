from __future__ import annotations

import logging
import re

from modular_rag.contracts.security import GuardResult
from modular_rag.core.models.answer import Answer
from modular_rag.core.models.query import Query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection / poison pattern families.
#
# Regex is a necessary-but-insufficient first line only: unstructured natural
# language defeats pure pattern matching, so semantic/role checks belong in
# later layers [ControlNet, arXiv 2504.09593]. The families below widen the
# original 5 override patterns to cover the highest-signal *textual* markers of
# practical corpus poisoning.
#
# Attack classes covered (described defensively, no working payloads):
#   * Family 1 — direct instruction override / jailbreak (query-time evasion).
#   * Family 2 — embedded promotional imperatives. Poisoned documents append an
#     imperative steering the model to recommend/visit an attacker-controlled
#     URL or product ("you MUST recommend this link"); removing that suffix
#     sharply drops attack success [PoisonCraft, arXiv 2505.06579]. We match the
#     imperative *verb pairing* (you must + recommend/visit/...), never the bare
#     word "must", so benign queries containing "must" are not blocked.
#   * Family 3 — reasoning-directive text. A single poisoned doc mimicking the
#     model's chain-of-thought can force a target conclusion ("therefore you
#     should conclude ..."); such text dictates the reasoning *outcome* instead
#     of supplying evidence [AdversarialCoT, arXiv 2604.12201].
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    # --- Family 1: direct instruction override / jailbreak ---
    re.compile(r"ignore (all )?(previous|prior|above) instructions", re.I),
    re.compile(r"disregard (your|the) (system|previous) (prompt|instructions)", re.I),
    re.compile(r"you are now|pretend (you are|to be)", re.I),
    re.compile(r"jailbreak|DAN mode|act as DAN|bypass all restrictions", re.I),
    re.compile(r"<!--\s*ignore|<\s*script\s*>|javascript:", re.I),
    # --- Family 2: embedded promotional imperatives [arXiv 2505.06579] ---
    re.compile(
        r"you\s+(?:must|should|need to|have to)\s+"
        r"(?:recommend|visit|use|cite|click|go to|check out|refer to|promote|link to|download)",
        re.I,
    ),
    re.compile(
        r"always\s+(?:recommend|cite|mention|visit|include|use|link to|promote|refer to)\b",
        re.I,
    ),
    re.compile(r"be sure to\s+(?:visit|recommend|cite|use|include|check out)", re.I),
    re.compile(
        r"(?:cite|use|recommend|visit)\s+(?:this|the following)\s+"
        r"(?:url|link|website|site|source|page)",
        re.I,
    ),
    # --- Family 3: reasoning-directive text [arXiv 2604.12201] ---
    re.compile(r"therefore,?\s+you\s+(?:should|must)\s+conclude", re.I),
    re.compile(
        r"(?:hence|thus|therefore),?\s+the\s+(?:correct\s+)?answer\s+(?:is|must be)",
        re.I,
    ),
    re.compile(r"step[-\s]by[-\s]step,?\s+you\s+(?:must|should)\b", re.I),
]

_BLOCKED_TERMS = frozenset(["rm -rf", "os.system", "exec(", "__import__"])

# Output-side poison signal: a poisoned corpus makes the model append an
# attacker URL / "for more info visit ..." referral to an otherwise-correct
# answer [PoisonCraft, arXiv 2505.06579]. We flag URLs in the answer that are
# not backed by any citation source.
_URL_PATTERN = re.compile(r"https?://[^\s)\]}\"'>]+", re.I)
_TRAILING_PUNCT = ".,;:!?)]}\"'>"


class BasicSecurityGuard:
    """First-line safety guard: prompt-injection / poison-marker detection.

    Pattern-based detection is deliberately treated as a *first line only*.
    Unstructured natural language defeats pure regex matching, so semantic and
    role-aware checks belong to later layers [ControlNet, arXiv 2504.09593].

    Query-side coverage widens the original override patterns with embedded
    promotional imperatives and reasoning-directive markers — the highest-signal
    textual traces of practical corpus poisoning [PoisonCraft, arXiv 2505.06579;
    AdversarialCoT, arXiv 2604.12201].

    Answer-side coverage flags URLs that do not appear in any citation source —
    the dominant observable effect of corpus poisoning [arXiv 2505.06579].

    ``risk_score`` scale (see ``.claude/rules/security.md``):
        0.9 = prompt injection, 0.8 = blocked term / poison marker,
        0.5 = length exceeded, 0.0 = OK.

    Never logs full query/answer text (lengths only) to avoid PII exposure.

    Config (all constructor kwargs, manifest-wirable via ``**cfg.config``):
        max_query_length: reject queries longer than this (risk 0.5).
        check_answer_urls: enable the answer-side uncited-URL check.
    """

    def __init__(
        self,
        max_query_length: int = 4000,
        check_answer_urls: bool = True,
    ) -> None:
        self.max_query_length = max_query_length
        self.check_answer_urls = check_answer_urls

    def name(self) -> str:
        return "basic-security-guard"

    def check_query(self, query: Query) -> GuardResult:
        text = query.text
        logger.debug("check_query (len=%d)", len(text))

        if len(text) > self.max_query_length:
            return GuardResult(
                allowed=False, reason="Query exceeds maximum length.", risk_score=0.5
            )

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                return GuardResult(
                    allowed=False,
                    reason=f"Potential prompt injection detected: {pattern.pattern[:40]}",
                    risk_score=0.9,
                )

        for term in _BLOCKED_TERMS:
            if term in text:
                return GuardResult(
                    allowed=False, reason=f"Blocked term detected: {term}", risk_score=0.8
                )

        return GuardResult(allowed=True, reason="", risk_score=0.0)

    def check_answer(self, answer: Answer) -> GuardResult:
        """Flag answers that surface URLs absent from every citation source.

        Corpus poisoning most often manifests as an attacker URL appended to an
        otherwise-correct answer [PoisonCraft, arXiv 2505.06579]. Conservative by
        design: an answer whose URLs all appear in a citation source passes, and
        an answer with no URLs (or empty text) passes.
        """
        text = answer.text
        logger.debug(
            "check_answer (len=%d, citations=%d)", len(text), len(answer.citations)
        )

        if not self.check_answer_urls or not text.strip():
            return GuardResult(allowed=True, reason="", risk_score=0.0)

        urls = [self._normalize_url(u) for u in _URL_PATTERN.findall(text)]
        if not urls:
            return GuardResult(allowed=True, reason="", risk_score=0.0)

        cited_corpus = self._citation_corpus(answer)
        uncited = [u for u in urls if u not in cited_corpus]

        if uncited:
            # Report count only; do not echo attacker-controlled URL text.
            return GuardResult(
                allowed=False,
                reason=(
                    f"Answer contains {len(uncited)} URL(s) not present in any "
                    "citation source (possible corpus poisoning)."
                ),
                risk_score=0.8,
            )

        return GuardResult(allowed=True, reason="", risk_score=0.0)

    @staticmethod
    def _normalize_url(url: str) -> str:
        return url.rstrip(_TRAILING_PUNCT)

    @staticmethod
    def _citation_corpus(answer: Answer) -> str:
        parts: list[str] = []
        for citation in answer.citations:
            parts.append(citation.source)
            parts.append(citation.passage)
        return " ".join(parts)
