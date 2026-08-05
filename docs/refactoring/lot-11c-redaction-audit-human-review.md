# Lot 11c — Redaction, Governed-Execution Audit Evidence, and Human Review

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** Lot 11b (identity/tenant context — "to know what to redact and for whom"), Lot 10
(`AuditEvent`/`AuditSink`, `GUARD_DECISION` event type already reserved but unused until now).

## What was done

Per `docs/refactoring-plan.md`: "Apply configured redaction before storage, logging, and external
calls; emit audit evidence for every governed execution; support human review for high-risk
outcomes."

### Redaction wiring

- **`Container.redactor`** (new optional property, mirrors every other optional component).
- **`RAGEngine._run_steps()`**: after the answer-guard step, if a `redactor` is configured, the
  answer text is redacted (`ans.text = redactor.redact(ans.text)`) before the `Answer` is returned
  to the caller.
- **`RAGEngine._audit()`**: if a `redactor` is configured, every audit event's payload gains a
  `query_text_redacted` key (already present in `contracts/audit.py`'s `ALLOWED_PAYLOAD_KEYS`
  since Lot 10, unused until now) with the redacted query text. **Without** a redactor configured,
  no query text — redacted or not — is added to the payload at all: omission over an unredacted
  fallback, matching the allowlist's own safety intent.
- Logging was already safe before this lot: `BasicSecurityGuard`'s own docstring states "Never
  logs full query/answer text (lengths only)" and `structlog` calls throughout `engine.py` already
  log only counts/lengths — verified, not re-implemented.

### Audit evidence for every governed execution

Previously, only the generic run-level `RUN_SUCCEEDED`/`RUN_FAILED` events existed (Lot 10). This
lot adds a specific `GUARD_DECISION` event **at the point of denial**, in addition to (not instead
of) the generic one:

- Tenant-isolation denial (`tenant_policy.enforce_query()` raising): caught, audited
  (`guard_decision: denied`, `error_type`), then **always re-raised unchanged** — this is
  audit-then-reraise, not exception-swallowing; fail-closed behavior from Lot 11b is unaffected.
- Query-guard denial (`guard.check_query()` returning `allowed=False`): audited
  (`guard_decision: denied`, `guard_reason`) before the `SecurityError` is raised.
- Answer-guard denial (`guard.check_answer()` returning `allowed=False`): same pattern.
- Human-review flagging (see below): audited (`guard_decision: flagged_for_review`).

Existing tests asserting "exactly one audit event" on a guard denial were updated to check for the
*specific* `GUARD_DECISION` event in addition to the pre-existing `RUN_FAILED` one — two events
per denial is the intended outcome, not a regression
(`tests/unit/orchestration/test_engine.py::test_answer_records_a_guard_decision_audit_event_when_guard_blocks_query`).

### Human review for high-risk outcomes

- **`contracts/review.py`** (new): `ReviewItem` (Pydantic model: `answer_id`, `query_id`,
  `tenant_id`, `reason`, `confidence`, `resolved`/`approved`/`reviewer` for later resolution) and
  the `ReviewQueue` Protocol (`should_review`, `enqueue`, `resolve`, `name`). Kept distinct from
  `AuditSink`: an `AuditEvent` is immutable compliance evidence of what happened; a `ReviewItem` is
  a mutable pending task someone acts on.
- **`security/policies/human_review.py`**: `HumanReviewGate` — a real in-memory reference
  `ReviewQueue` implementation (not a mock), `threshold: float = 0.7` matching the
  previously-aspirational number already written in `docs/architecture/security.md`'s risk-level
  table ("require_review for high-risk answers (confidence < 0.7)") — this lot wires that number
  into real, callable code for the first time.
- **`Container.review_queue`** (new optional property) and `RAGEngine._run_steps()` step 7: after
  redaction, if a `review_queue` is configured and `should_review(ans)` is true, the answer gains
  `metadata["requires_review"] = True`, a `ReviewItem` is enqueued, and a `GUARD_DECISION` audit
  event is recorded.

## Honesty note (recorded here and in `human_review.py`'s own docstring, not hidden)

Today, **no generator sets `Answer.confidence` on a normal, shipped answer** — the only code path
that sets it at all is `GroundednessValidator.refusal_answer()` (sets `confidence=0.0` on a
refusal), and `GroundednessValidator` itself is not wired into `RAGEngine`'s pipeline. This means
`HumanReviewGate` is real, tested, and will correctly flag whatever answer carries a low
`confidence`, but as currently wired end-to-end it has no live trigger from real generators.
Connecting a genuine confidence/quality signal to `Answer.confidence` for real, shipped answers is
squarely `docs/refactoring-plan.md`'s Lot 13 scope ("measure retrieval, answer, evidence, policy,
latency, and cost"), not this one. Recorded as a known limitation, not silently left implicit.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 388 tests total (315 unit + 73 contract, up from 366 at Lot 11b).
- mypy baseline unchanged at 35.
- Redaction: proven against a real `PatternRedactor` (not a mock) — answer text and audit payload
  query text both redacted when configured, both left untouched (text) or omitted (audit payload)
  when not.
- Human review: proven against a real `HumanReviewGate` — low-confidence answers flagged and
  queued, high-confidence and unset-confidence answers are not.
- Fail-closed regression from Lot 11b unaffected: the new audit-then-reraise wrapping around
  `tenant_policy.enforce_query()` still always re-raises; no test needed updating for that
  invariant because the exception path itself didn't change, only the side-effect before it.

## Lot 11c acceptance (per `docs/refactoring-plan.md` §11c bullet)

"Every governed execution has redaction, policy, and audit evidence attached" — for every guard
(query/answer), tenant-isolation, and human-review decision point, a `GUARD_DECISION` audit event
now fires alongside the pre-existing generic run-level event; redaction (when configured) is
applied to both the returned answer and any audit payload query text before either leaves the
process boundary.

## Next

This completes Phase C's Lot 11 (11a, 11b, 11c). Lot 12a (document lifecycle: identity, idempotent
ingestion, update, deletion, tombstone semantics — PostgreSQL-backed, consistent with Lot 10's
audit-store choice) is next.
