# Lot 16a — API/CLI Hardening

**Date:** 2026-08-05
**Status:** COMPLETE

## Scope (from `docs/refactoring-plan.md` §5, Phase D)

> Harden FastAPI factory/startup, typed safe errors, authentication, authorization, rate and
> request-size limits, readiness/liveness, content exposure, and CLI exit codes.

This closes two gap-matrix rows: "API security" (CRITICAL — no auth, rate limits, or
request-size limits; internal exception strings and source content can leak to callers) and the
residual half of "Tenant isolation" from Lot 11b ("no API/CLI authentication middleware calls
the verifier yet").

## What was built

| File | Purpose |
|---|---|
| `src/modular_rag/api/errors.py` (new) | `to_http_exception()` — typed-safe HTTP error mapping. `AuthenticationError` → 401, `SecurityError`/`PolicyViolationError` → 403 (their own message is the safe, caller-facing explanation — the same convention `SecurityGuard.check_query()`'s `reason` already follows). Everything else → generic 500/502 message plus a correlation id; the real exception is logged in full server-side under that id, never returned to the caller. |
| `src/modular_rag/api/middleware.py` (new) | `MaxBodySizeMiddleware` (413 over a configurable byte limit, checked against `Content-Length` before the body is read) and `RateLimitMiddleware` (429 with `Retry-After`, fixed-window, `threading.Lock`-guarded in-memory per-client state — mirrors Lot 14's precedent for the other in-memory reference stores with a genuine read-then-write race). Both exempt `/health`/`/ready`. |
| `src/modular_rag/api/__init__.py` | `create_app()` gained `token_verifier`, `max_body_bytes`, `rate_limit_per_minute` parameters (all optional, default-open/default-permissive — matching every other optional-component precedent: guard, redactor, tenant_policy). New `/ready` route (see honesty note below). `/answer`/`/retrieve` now run through `_authenticate()` (an `HTTPBearer`-based FastAPI dependency) and both call `to_http_exception()` instead of `except Exception: raise HTTPException(status_code=500, detail=str(exc))`. |
| `src/modular_rag/orchestration/engine.py` | `RAGEngine.retrieve()` gained `tenant_id` and now enforces/filters through `Container.tenant_policy` — see the bug below. |
| `src/modular_rag/cli/__init__.py` | `ingest`/`ask` wrapped in try/except with typed exit codes (`EXIT_CONFIGURATION_ERROR=2`, `EXIT_SECURITY_DENIAL=3`, `EXIT_OPERATION_ERROR=4`, `1` for anything else) instead of an uncaught Python traceback. `ask` gained `--tenant-id`. |
| `docs/api/rest.md` | Rewritten to match current behavior — it still described the pre-Lot-8 `/answer` routing bug as current and said "no built-in authentication... V4 will add" (both stale; the routing bug was fixed in Lot 8, and per ADR-0005 the policy engine and tenant/identity plane are owned-and-current, not V4-deferred). |
| Tests | `tests/unit/api/test_api.py`: rewrote the two tests that used to characterize the leak/no-auth gaps as regression tests proving the fix, plus new coverage for `/ready`, 401/403 mapping, tenant-id threading from a verified token, 413, and 429. `tests/unit/orchestration/test_engine.py`: 3 new tests for the `retrieve()` tenant-isolation fix. `tests/unit/cli/test_cli.py`: `--tenant-id` threading, typed exit codes for a security denial and a configuration error. |

## A genuine bug found while wiring auth: `RAGEngine.retrieve()` bypassed tenant isolation entirely

While wiring `/retrieve` to the new `_authenticate()` dependency, threading the verified
`tenant_id` through revealed that `RAGEngine.retrieve()` built a bare `Query(text=question)`
and called `_retrieve()` directly — it never consulted `Container.tenant_policy` at all, unlike
`answer()`, whose `_run_steps()` both enforces `tenant_policy.enforce_query()` before retrieval
and filters cross-tenant chunks after it (Lot 11b). This meant that even with an authenticated
tenant identity available, `/retrieve` (and any direct `RAGEngine.retrieve()` caller) could
return any tenant's chunks — auth alone would have been theater without this fix, since the
authenticated tenant_id had nowhere to be enforced on this path. Fixed: `retrieve()` now takes
`tenant_id: str | None = None`, calls `tenant_policy.enforce_query()` before retrieving, and
`tenant_policy.filter_chunks()` after — the identical two steps `_run_steps()` performs, just
without the trace/audit instrumentation `answer()`'s full pipeline has (that remains `answer()`
-specific; `retrieve()` has never emitted trace/audit evidence and this lot didn't add it).
Regression tests: `test_retrieve_raises_when_tenant_policy_configured_and_no_tenant_id_given`,
`test_retrieve_filters_cross_tenant_chunks`.

## Authentication: optional, real, structurally the same shape as everything else optional

`create_app(..., token_verifier=None)` — a `contracts.identity.TokenVerifier`
(`KeycloakTokenVerifier`, Lot 11b, is the reference implementation). `None` (default) leaves
every route open, matching `guard`/`redactor`/`tenant_policy`'s own optionality precedent rather
than inventing a new pattern. When configured, `_authenticate()` (an `HTTPBearer`-based FastAPI
dependency, `auto_error=False` so a missing header maps to this module's own 401, not
`HTTPBearer`'s generic one) verifies the bearer token and returns a `TenantContext`; its
`tenant_id` — never a request field — is what gets threaded into `pipeline.answer()`/
`.retrieve()`. There is no way for a caller to claim a tenant identity except through a token
that verifies.

Tested with `_FakeTokenVerifier`, a genuine (not mocked) `TokenVerifier` conformant
implementation backed by a fixed in-memory token table — `KeycloakTokenVerifier` itself already
proves the real RS256/JWKS path against a generated keypair (Lot 11b); this fake exists so API
tests prove the *wiring* (auth required, 401 on missing/invalid token, tenant_id threaded
through) without needing a live/simulated identity provider in this test.

## Typed safe errors: what's caller-facing vs. what's generic

Two exception families are treated as genuinely caller-facing, because their message already
*is* the safe explanation a caller needs — this mirrors the existing convention elsewhere in the
codebase (`SecurityGuard.check_query()` returns a human-readable `reason` precisely so it can be
shown to the caller):

- `AuthenticationError` → 401, message passed through.
- `SecurityError` (covers `PolicyViolationError`) → 403, message passed through.

Everything else — `ConfigurationError` (may contain server-side manifest paths),
retrieval/generation/ingestion/storage failures, or a non-framework exception — gets a generic
500/502 message plus a correlation id (`uuid4`); the real exception (type + full message) is
logged server-side via `structlog` (`api.request_failed`) under that same id. A support
engineer can find the real cause from the id; a caller never sees raw internals, stack
fragments, connection strings, or file paths.

## Rate limit and request-size limit: real, tested, and honestly scoped

Both are genuine in-process implementations proven with real `TestClient` requests (not stubs) —
`RateLimitMiddleware`'s fixed window is `threading.Lock`-guarded exactly like Lot 14's four
in-memory reference stores. Scoped honestly: state is per-process, so a horizontally-scaled
deployment (more than one worker/replica) would rate-limit each replica independently rather than
sharing one global counter. The middleware docstring records the Redis-backed upgrade path
rather than silently implying it. `/health` and `/ready` are excluded from both — an
orchestrator's own probes must never trip a rate limit or get rejected for a body-size check on
requests they don't control.

## Readiness/liveness: honest, not aspirational

`/health` (liveness) and `/ready` (readiness) currently return identical evidence — that
`create_app()` finished wiring successfully. This lot deliberately did **not** invent live
connectivity probing (pinging Qdrant, checking an LLM API key is valid) because no adapter in
this codebase exposes a cheap, uniform health-check method today; building one would be a real
`contracts/` addition affecting every adapter, out of this lot's scope. `/ready`'s docstring says
this explicitly rather than letting the route name imply more than it delivers — consistent with
Lot 5's capability-truth discipline.

## CLI exit codes

Previously every CLI failure mode — a typo'd manifest path, a security-guard denial, a genuine
ingestion/retrieval crash — surfaced identically as an uncaught Python traceback with exit code
1. A caller scripting against this CLI (CI, a shell pipeline) could not distinguish "your input
was invalid" from "the framework broke" without parsing stderr text. `ingest`/`ask` now catch
`Exception`, print a clean one-line `ERROR: ...` to stderr, and exit with a code selected by
exception type: `2` (`ConfigurationError`/`ManifestError`), `3` (`SecurityError`/
`PolicyViolationError`), `4` (any other `ModularRAGError`), `1` (anything else, preserving the
previous default for truly unexpected failures). `ask` also gained `--tenant-id`, closing a
related gap: without it, `ask` could never successfully call a tenant-policy-enabled manifest at
all (there was no way to supply the identity `answer()` requires).

## Deliberately out of scope, recorded honestly

- CLI does not gain token-based authentication. The CLI operates with direct filesystem/manifest
  access — an operator who can point it at a manifest already has more trust than an anonymous
  network caller of the API; "auth" for a local CLI tool is a different problem (OS-level access
  control) this lot doesn't invent a framework-level answer for.
- `ingest`'s tenant_id is unchanged — it comes from `Document.tenant_id` at ingestion-pipeline
  construction time (Lot 11b scope), not a new CLI flag; adding one would need to thread through
  `ingest_path`/`ingest_directory`'s per-document construction, a larger change than this lot's
  "auth/errors/limits" scope.
- No horizontally-scaled/shared-store rate limiting (Redis) — recorded as the documented upgrade
  path, not built, since this environment has no such infrastructure to build and test against.
- `/ready` does not probe live dependency connectivity — recorded above.

## Verification

`./scripts/check.sh full` — all 7 steps pass:

1. Ruff — clean (3 `B008` false-positives on FastAPI's idiomatic `Depends(...)` in argument
   defaults suppressed with `# noqa: B008`, matching the CLI's own existing `typer.Argument`/
   `typer.Option` precedent).
2. Compilation — clean.
3. Hexagonal layering audit — clean (`api/`/`cli/` are unrestricted layers per
   `scripts/check_layering.py`; no new violation).
4. mypy — **31 errors (baseline lowered 34 → 31)**: fixed the pre-existing untyped bare `dict`
   return annotations in `api/__init__.py` (`health()`, `retrieve()`, `AnswerResponse.citations`)
   while adding the new `/ready` route, rather than adding a fourth alongside them.
5. Runnable manifest validation — unaffected.
6. Unit tests — 465 passed (16 new/changed in `test_api.py`, 3 new in `test_engine.py`, 3 new in
   `test_cli.py`).
7. Contract tests — 82 passed, unaffected.

## Tracker updates

- Header status block: Lot 16a → COMPLETE.
- Gap matrix: "API security" row resolved. "Tenant isolation" residual row's "no API/CLI
  authentication middleware" sub-item resolved; the `retrieve()` bypass bug found and fixed here
  is called out explicitly since it was a real, previously-undiscovered gap, not anticipated by
  Lot 11b's own record.
- Decision log + change history: new Lot 16a entry.
