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

# Codex review HIGH-003 (Lot 6, third pass): see `openai_gen.py`'s identical
# constant for the full rationale.
_HEALTH_CHECK_CACHE_SECONDS = 30.0
# Codex review HIGH-002 (Lot 6, fourth pass): see `openai_gen.py`'s
# identical constants for the full rationale — both installed SDKs default
# to `max_retries=2` with `self.timeout` (30s), verified live.
_HEALTH_CHECK_TIMEOUT = 5.0
_HEALTH_LOCK_ACQUIRE_TIMEOUT = 2.0


def _unhealthy(name: str, exc: Exception, latency_ms: float) -> DependencyHealth:
    """Codex review MEDIUM-001 (Lot 6, third pass): see
    `openai_gen.py`'s identical helper for the full rationale — domain
    modules may import only `contracts/` + `core/models/`."""
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


class AnthropicGenerator:
    """Generate grounded answers via the Anthropic Messages API."""

    def __init__(
        self,
        model: str = "claude-opus-4-7",
        max_tokens: int = 2048,
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.timeout = timeout
        self._client: object | None = None
        self._groundedness = GroundednessValidator()
        # Codex review HIGH-003 (Lot 6, third pass): see
        # `OpenAIGenerator`'s identical fields for the full rationale.
        self._health_lock = threading.Lock()
        self._health_cache: tuple[float, list[DependencyHealth]] | None = None

    def name(self) -> str:
        return "anthropic"

    def _get_client(self) -> object:
        if self._client is None:
            try:
                import anthropic

                self._client = anthropic.Anthropic(
                    api_key=self.api_key or None, timeout=self.timeout
                )
            except ImportError as exc:
                raise ImportError("Install 'anthropic' (pip install modular-rag[v1]).") from exc
        return self._client

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        return "\n\n".join(
            f"[{i}] {rc.chunk.metadata.get('source', 'unknown')}\n{rc.chunk.content}"
            for i, rc in enumerate(chunks, 1)
        )

    def generate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        client = self._get_client()
        ctx_text = self._build_context(context)
        t0 = time.perf_counter()
        response = client.messages.create(  # type: ignore[union-attr]
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Context:\n{ctx_text}\n\nQuestion: {query.text}"}
            ],
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        trace.add_step(
            TraceStep(
                name="anthropic_generate",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=latency_ms,
                metadata={"model": self.model},
            )
        )
        text = response.content[0].text
        answer = Answer(
            query_id=query.id,
            text=text,
            citations=build_citations(context),
            model=self.model,
        )
        if self._groundedness.should_refuse(answer, context):
            return self._groundedness.refusal_answer(answer)
        return answer

    async def agenerate(self, query: Query, context: list[RetrievedChunk], trace: Trace) -> Answer:
        return self.generate(query, context, trace)

    def close(self) -> None:
        """Release the underlying anthropic client, if one was ever opened
        (Lot 14, docs/refactoring-plan.md — "own and close clients/
        resources")."""
        if self._client is not None:
            self._client.close()  # type: ignore[attr-defined]
            self._client = None

    def check_health(self) -> list[DependencyHealth]:
        """Implements `contracts.health.HealthCheckable` (Codex review
        HIGH-001, second pass — see `OpenAIGenerator.check_health()` for
        the shared rationale: no generator previously implemented this at
        all, so an unreachable provider or a missing API key left `/ready`
        green while every real `/answer` call failed).

        Codex review HIGH-003 (Lot 6, third pass): the prior version of
        this method checked only whether a credential string was
        configured — necessary but not sufficient, since a revoked/
        malformed/expired/over-quota key is still a non-empty string.
        This now makes a real, authenticated, non-generative call.

        Codex review HIGH-004 (Lot 6, fourth pass): that call was
        `client.models.list()`, whose result was discarded — a valid key
        for *any* model was enough to report healthy even if `self.model`
        itself (the one `generate()` actually uses) was misspelled,
        retired, or inaccessible to this account. Switched to
        `client.models.retrieve(self.model)`, which 404s specifically when
        the configured model isn't available to this key (verified live
        against the real API).

        Codex review HIGH-002 (Lot 6, fourth pass): the call previously
        went through the shared, cached `self._client` unmodified —
        inheriting `self.timeout` (30s, sized for a real generation call)
        and the SDK's own default `max_retries=2` (verified live on the
        installed version), contradicting ADR-0010's "single, short,
        bounded attempt" rule.
        `client.with_options(timeout=_HEALTH_CHECK_TIMEOUT, max_retries=0)`
        overrides both per call, on a lightweight view of the client,
        without mutating `self._client` (verified live). `self._health_lock`
        is now acquired with a bound too (`_HEALTH_LOCK_ACQUIRE_TIMEOUT`)
        rather than indefinitely — a probe stuck despite the above must not
        also block every other concurrent `/ready` call behind the same
        lock; a timed-out acquire reports "busy" rather than hanging.

        Cached for `_HEALTH_CHECK_CACHE_SECONDS` (refreshes serialized by
        the same lock into one real call) — see
        `OpenAIGenerator.check_health()` for why this matters on an
        unauthenticated, rate-limit-exempt route. Residual, documented
        limitation: same as `OpenAIGenerator` — validates the credential
        against the specific configured model, not a full end-to-end
        `generate()` call. See ADR-0010.
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
