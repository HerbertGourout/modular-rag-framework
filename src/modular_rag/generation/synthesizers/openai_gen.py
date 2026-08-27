from __future__ import annotations

import threading
import time
import uuid

import structlog

from modular_rag.core.models.answer import Answer
from modular_rag.core.models.health import DependencyHealth
from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk
from modular_rag.core.models.trace import Trace, TraceStep
from modular_rag.core.pricing import estimate_cost_usd
from modular_rag.generation.citations.builder import build_citations
from modular_rag.generation.validators.groundedness import GroundednessValidator

log = structlog.get_logger(__name__)

# Negative-rejection clause per arXiv:2404.10981 §7.1 (Negative Rejection is a
# first-class responsible-generation metric): instructing the model to decline
# when the context lacks the answer is a low-cost hallucination reduction for V1.
_SYSTEM_PROMPT = """\
You are a precise assistant. Answer the user's question using ONLY the provided context.
Cite the source of each claim. If the context is insufficient, say so explicitly.
If the context does not contain the answer, say you don't know — do not guess.
"""

# Codex review HIGH-003 (Lot 6, third pass): a real, authenticated
# `models.list()` call now backs `check_health()` — bounding how often it
# actually reaches the provider, since `/ready` is unauthenticated and
# could be probed far more often than any provider's own rate limit
# tolerates. `check_health()`'s own docstring has the full rationale.
_HEALTH_CHECK_CACHE_SECONDS = 30.0
# Codex review HIGH-002 (Lot 6, fourth pass): the probe must never inherit
# `self.timeout` (30s, sized for a real generation call) or the SDK's own
# default `max_retries=2` — both installed SDKs default to that, verified
# live — since ADR-0010 requires a probe to be a single, short, bounded
# attempt. Passed to `client.with_options(...)` per call, never mutating
# the shared, cached `self._client`.
_HEALTH_CHECK_TIMEOUT = 5.0
# Bound on how long check_health() waits for a concurrent cache-miss
# refresh to finish, rather than blocking indefinitely. (The Postgres
# adapters carried an identically-named constant for a similar purpose
# through Lot 6's fourth pass; their check_health() redesign in the fifth
# pass removed it entirely — see ADR-0010 §4 — so this name is now specific
# to the LLM generators' own cache lock.)
_HEALTH_LOCK_ACQUIRE_TIMEOUT = 2.0


def _unhealthy(name: str, exc: Exception, latency_ms: float) -> DependencyHealth:
    """Codex review MEDIUM-001 (Lot 6, third pass): domain modules
    (`generation/`) may import only `contracts/` + `core/models/` per
    `CLAUDE.md` §02 — `core.resilience.unhealthy_dependency()` (used freely
    by `adapters/`, which has no such restriction) is out of bounds here.
    Inlined locally instead of sharing that helper — same behavior (a
    stable, non-sensitive code plus a correlation id; the full exception,
    which can embed request/response internals, is logged server-side via
    this module's own `log`, never returned in the public `/ready` body)."""
    correlation_id = uuid.uuid4().hex[:8]
    log.warning(
        "dependency_check_failed",
        dependency=name,
        correlation_id=correlation_id,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    text = str(exc).lower()
    code = "timeout" if "timeout" in text or "timed out" in text else "unreachable"
    return DependencyHealth(
        name=name, healthy=False, detail=f"{code} ({correlation_id})", latency_ms=latency_ms
    )


class OpenAIGenerator:
    """Generate grounded answers via the OpenAI Chat API."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        # Low-variance engineering default, unsourced by the research corpus
        # (docs/research/DIGEST-generation.md #7) — sweep during V1.1 evaluation.
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.timeout = timeout
        self._client: object | None = None
        self._groundedness = GroundednessValidator()
        # Codex review HIGH-003 (Lot 6, third pass): guards
        # `_health_cache` and serializes concurrent cache-miss refreshes —
        # without it, several `/ready` calls arriving while the cache is
        # expired would each fire their own real provider request
        # simultaneously (a self-inflicted rate-limit/thundering-herd
        # risk) instead of one refreshing it for all of them.
        self._health_lock = threading.Lock()
        self._health_cache: tuple[float, list[DependencyHealth]] | None = None

    def name(self) -> str:
        return "openai"

    def _get_client(self) -> object:
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key or None, timeout=self.timeout)
            except ImportError as exc:
                raise ImportError("Install 'openai' (pip install modular-rag[v1]).") from exc
        return self._client

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        parts = []
        for i, rc in enumerate(chunks, 1):
            source = rc.chunk.metadata.get("source", "unknown")
            parts.append(f"[{i}] Source: {source}\n{rc.chunk.content}")
        return "\n\n".join(parts)

    def generate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        client = self._get_client()
        ctx_text = self._build_context(context)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{ctx_text}\n\nQuestion: {query.text}"},
        ]
        t0 = time.perf_counter()
        response = client.chat.completions.create(  # type: ignore[union-attr]
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        usage = response.usage
        metadata: dict[str, object] = {"model": self.model}
        cost_usd = estimate_cost_usd(self.model, usage.prompt_tokens, usage.completion_tokens)
        if cost_usd is not None:
            metadata["cost_usd"] = cost_usd
        trace.add_step(
            TraceStep(
                name="openai_generate",
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                latency_ms=latency_ms,
                metadata=metadata,
            )
        )
        text = response.choices[0].message.content or ""
        citations = build_citations(context)
        log.debug("openai.generated", tokens=usage.total_tokens, ms=latency_ms)
        answer = Answer(query_id=query.id, text=text, citations=citations, model=self.model)
        if self._groundedness.should_refuse(answer, context):
            return self._groundedness.refusal_answer(answer)
        return answer

    async def agenerate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        return self.generate(query, context, trace)

    def close(self) -> None:
        """Release the underlying openai client, if one was ever opened
        (Lot 14, docs/refactoring-plan.md — "own and close clients/
        resources")."""
        if self._client is not None:
            self._client.close()  # type: ignore[attr-defined]
            self._client = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Codex review
        HIGH-001, second pass — no `OpenAIGenerator`/`AnthropicGenerator`
        previously implemented this at all, so an unreachable provider or a
        missing API key left `/ready` green while every real `/answer`
        call failed).

        Codex review HIGH-003 (Lot 6, third pass): the prior version of
        this method validated only that a client could be *constructed* —
        a credential-presence check. `generator` is a **critical** role
        (`orchestration.container._CRITICAL_ROLES`): a revoked, malformed,
        expired, or over-quota key passed that check and reported
        `healthy` while every real `/answer` call would fail — verified
        live with a deliberately invalid key. This now makes a real,
        authenticated, non-generative call.

        Codex review HIGH-004 (Lot 6, fourth pass): that call was
        `client.models.list()`, whose result was discarded — a valid key
        for *any* model was enough to report healthy even if `self.model`
        itself (the one `generate()` actually uses) was misspelled,
        retired, or inaccessible to this account. Switched to
        `client.models.retrieve(self.model)`, which 404s specifically when
        the configured model isn't available to this key (verified live:
        both a bad key and, separately, `models.retrieve()`'s call shape
        against a real, syntactically valid model id both behave as
        expected against the real API).

        Codex review HIGH-002 (Lot 6, fourth pass): the call previously
        went through the shared, cached `self._client` unmodified — meaning
        the probe inherited `self.timeout` (30s, sized for a real
        generation call, not a readiness probe) and the SDK's own default
        `max_retries=2` (verified live on the installed version), directly
        contradicting ADR-0010's "single, short, bounded attempt" rule; a
        network partition could hold a probe for minutes across retries.
        `client.with_options(timeout=_HEALTH_CHECK_TIMEOUT, max_retries=0)`
        overrides both *per call*, on a lightweight view of the client,
        without mutating `self._client` (verified live: `with_options()`
        returns a distinct object; the shared client's own `.timeout`/
        `.max_retries` are unaffected). `self._health_lock` is now acquired
        with a bound too (`_HEALTH_LOCK_ACQUIRE_TIMEOUT`) rather than
        indefinitely — a probe stuck despite the above (DNS resolution
        hanging outside httpx's own timeout coverage, for instance) must
        not also block every other concurrent `/ready` call behind the same
        lock; a timed-out acquire reports "busy" rather than hanging.

        Cached for `_HEALTH_CHECK_CACHE_SECONDS` (refreshes serialized by
        the same lock into one real call): `/ready` is deliberately
        unauthenticated and exempt from rate limiting, so nothing else
        bounds how often it could be hit — without a cache, a real provider
        call on every single probe risks tripping the provider's own rate
        limit, which would then make `/ready` flap between healthy and
        unhealthy for reasons unrelated to the actual dependency's state.

        Residual, documented limitation: this still cannot distinguish "the
        model is fine but this key is out of quota for *some other* reason
        not tied to the model itself" from a real outage — narrower than a
        full end-to-end `generate()` call, but validates both the
        credential and the specific configured model, not just that some
        model is listed. See ADR-0010.
        """
        if not self._health_lock.acquire(timeout=_HEALTH_LOCK_ACQUIRE_TIMEOUT):
            return [DependencyHealth(name=self.name(), healthy=False, detail="busy")]
        try:
            now = time.monotonic()
            if self._health_cache is not None:
                cached_at, cached_result = self._health_cache
                if now - cached_at < _HEALTH_CHECK_CACHE_SECONDS:
                    return cached_result
            t0 = time.perf_counter()
            try:
                client = self._get_client()
                probe_client = client.with_options(  # type: ignore[attr-defined]
                    timeout=_HEALTH_CHECK_TIMEOUT, max_retries=0
                )
                probe_client.models.retrieve(self.model)
            except Exception as exc:
                result = [_unhealthy(self.name(), exc, (time.perf_counter() - t0) * 1000)]
            else:
                result = [
                    DependencyHealth(
                        name=self.name(), healthy=True, latency_ms=(time.perf_counter() - t0) * 1000
                    )
                ]
            self._health_cache = (now, result)
            return result
        finally:
            self._health_lock.release()
