# Lot 11b — Identity/Tenant Propagation

**Status:** COMPLETE
**Date:** 2026-08-05
**Depends on:** Lot 11a (data-classification/tenant vocabulary and fixtures), Lot 7
(`ExecutionContext.tenant_id`, already present as a required field), Lot 10 (`RAGEngine._audit()`'s
placeholder tenant lookup, now replaced with the real field).

## What was done

Per `docs/refactoring-plan.md`: "Propagate authenticated identity and tenant through
`ExecutionContext`; enforce fail-closed policy before indexing, retrieval, and generation. Test
cross-tenant and policy-engine failure paths (deny-by-default on policy-engine error, not
allow-by-default)."

### Identity/tenant now a real field, not just metadata

- **`core.models.query.Query.tenant_id: str | None = None`** (new field, additive — default `None`
  keeps every existing manifest/test unaffected). Same addition to **`core.models.chunk.Chunk`**
  and **`core.models.document.Document`**.
- **`ingestion/chunkers/fixed.py`, `ingestion/chunkers/adaptive.py`**: both now copy
  `document.tenant_id` onto every `Chunk` they produce — without this, `RAGEngine.ingest()`'s
  document path would silently drop tenant identity between `Document` and `Chunk`, defeating
  enforcement before it could ever run.
- **`RAGEngine._audit()`** (Lot 10) now reads `query.tenant_id` directly instead of the
  `query.metadata.get("tenant_id", "unknown")` placeholder — closing exactly the gap Lot 10's own
  decision record flagged as this lot's job.
- **`contracts/identity.py`** (new): `TenantContext` (frozen dataclass: `tenant_id`, `user_id`,
  `roles: frozenset[str]`) and the `TokenVerifier` Protocol. Vendor-neutral, same discipline as
  `contracts/engine.py` — no Keycloak/JWT types appear here.
- **`core/errors.py`**: `AuthenticationError(SecurityError)` — raised on any token-verification
  failure, never caught and downgraded to an anonymous identity.

### Keycloak adapter (external binding)

- **`adapters/auth/keycloak_verifier.py`** (new): `KeycloakTokenVerifier` — RS256 JWT verification
  against a Keycloak realm's JWKS endpoint (`{issuer}/protocol/openid-connect/certs`), with
  configurable dotted-path claim names (`tenant_claim`, `user_claim`, `roles_claim`, default
  `realm_access.roles` matching Keycloak's own default shape) since claims mapping is
  realm/client-specific, not fixed by this adapter. `httpx` (JWKS fetch) is a base project
  dependency already, imported at module level; `jwt` (PyJWT, `crypto` extra) is lazy-imported per
  `.claude/.instructions.md` §4 and **not declared in `pyproject.toml`** — same "opt-in
  infrastructure" precedent as `adapters/audit/postgres_sink.py` (Lot 10). Any verification
  failure (bad signature, expired, wrong audience/issuer, unknown `kid`, missing required claims)
  raises `AuthenticationError` — never falls through to a default identity.
- `.claude/settings.json`, `CLAUDE.md`, `.claude/rules/security-layers.md`,
  `.claude/rules/adapters.md`: `src/modular_rag/adapters/auth/**` moved from `deny` to `ask`,
  per CLAUDE.md's own standing instruction to "revisit at Lot 11b, don't open speculatively" — now
  that it is.

### Fail-closed enforcement

- **`security/policies/tenant_isolation.py`** (new): `TenantIsolationPolicy` — `enforce_query()`
  (deny if `Query.tenant_id` is falsy), `enforce_ingest()` (deny if a chunk has no `tenant_id`),
  `filter_chunks()` (keep only chunks whose `tenant_id` matches the query's; a chunk with no
  `tenant_id` at all — legacy/unclassified — is excluded too, not treated as implicitly public;
  documented as a follow-up once `Chunk` carries a classification field). Implements the new
  `contracts.security.TenantPolicy` Protocol. Registered on `Container.tenant_policy` — optional,
  mirrors `guard`/`audit_sink`'s precedent (Lots 8/10), so an unconfigured pipeline is unaffected.
- **`security/policies/policy_engine.py`**: `PolicyEngine.enforce_query()` now wraps rule
  evaluation in a `try`/`except` — any exception during `_evaluate()` raises `PolicyViolationError`
  ("denied by default (fail-closed)") instead of silently treating the rule as non-matching. This
  is the literal "policy-engine errors deny by default" acceptance criterion; today's
  keyword-matching `_evaluate()` can't itself throw on normal input, so this specifically protects
  against a future CEL/Rego evaluator (ADR-0003 §"Open item (V4)") raising a parse/evaluation
  error.
- **`orchestration/engine.py`**: `RAGEngine._run_steps()` calls `tenant_policy.enforce_query()` as
  the very first check (before the `SecurityGuard`), with **no `try`/`except` around it** — any
  exception, expected or not, propagates and blocks the run; that absence of exception-swallowing
  *is* the fail-closed mechanism, not a special-cased branch. After retrieval, a new tenant-filter
  step (`filter_chunks()`) removes cross-tenant/unclassified chunks before reranking or generation
  — emits a `tenant_filter` `TraceStep` with before/after counts. `ingest_chunks()` calls
  `enforce_ingest()` per chunk before any embedding/indexing work starts.
- **`orchestration/native_engine.py`**: `NativeEngineAdapter.run()` now forwards
  `context.tenant_id` into `RAGEngine.answer(..., tenant_id=context.tenant_id)` — this is the
  literal `ExecutionContext` propagation the plan names; previously the adapter read only
  `request.query.text`, silently dropping identity at the port boundary regardless of what a
  caller set on `ExecutionContext`.

## Verification

- `./scripts/check.sh full` — all 7 steps pass.
- 366 tests total (298 unit + 68 contract, up from 324 at Lot 11a).
- mypy baseline unchanged at 35.
- `KeycloakTokenVerifier` tested against **real** RS256 cryptographic signing/verification (a
  locally generated RSA keypair, `_get_jwks()` monkeypatched to serve the fixture's own JWKS — no
  live Keycloak, no network mocking needed): valid token accepted; expired, wrong-audience,
  wrong-issuer, forged-signature (same `kid`, different private key), unknown-`kid`, and
  missing-claim tokens all correctly rejected. `pyjwt[crypto]` was installed locally in this
  session's `.venv` to run this suite for real — it is **not** added to `pyproject.toml`, so a
  fresh `pip install -e ".[v1,dev]"` will not have it; `tests/unit/adapters/auth/test_keycloak_verifier.py`
  uses `pytest.importorskip("jwt")` and will skip cleanly in that case, consistent with the
  Postgres integration-test precedent from Lot 10 (real code, gracefully absent where its optional
  dependency isn't installed).
- Fail-closed regression test: `_RaisingPolicyEngine` (subclass forcing `_evaluate()` to raise)
  proves `PolicyEngine.enforce_query()` denies rather than silently passing the query.
- Cross-tenant regression test: `test_answer_filters_cross_tenant_chunks_before_generation` proves
  the generator never receives another tenant's chunks, not just that the final answer omits them.

## Known limitations (not closed by this lot)

- **Nothing calls `KeycloakTokenVerifier` yet.** `api/__init__.py` and `cli/__init__.py` still
  build `Query`/`EngineRequest` without extracting a bearer token or populating `tenant_id` from
  one — there is no authentication *middleware* wiring a verified `TenantContext` into a request.
  That is `docs/refactoring-plan.md`'s Lot 16a ("authentication, authorization") — this lot
  delivers the verifier and the enforcement mechanism it feeds, not the HTTP/CLI entry-point
  wiring. A caller today can still set `tenant_id` directly (e.g. `mrag ask --tenant-id ...`, not
  yet added either), but nothing authenticates that claim.
- **Filtering happens after retrieval, not at query time.** `TenantIsolationPolicy.filter_chunks()`
  runs against whatever `VectorRetriever`/`HybridRetriever` already fetched from Qdrant — other
  tenants' chunks are still *fetched* from the shared collection and then discarded, not excluded
  by the vector-store query itself. This is correct as a defense-in-depth layer (matches the
  threat model's Elevation-of-Privilege row, docs/architecture/threat-model.md §4) but is not
  query-time partitioning; `QdrantStore` has no tenant-scoped collection/filter parameter yet.
  Flagged for Lot 12b (index schema/reconciliation) to evaluate — tightening this is a
  performance/leakage-surface improvement, not a correctness gap given the post-fetch filter is
  unconditional and fail-closed.
- **`public`-classified content has no bypass.** Per `data-classification-policy.md` §1, a `public`
  document should be visible to any tenant. `Chunk` has no classification field, only `tenant_id`,
  so `filter_chunks()` cannot distinguish "public, safe to share" from "unclassified, deny by
  default" — it treats both identically (excluded unless the tenant matches exactly). Documented
  as a follow-up in `tenant_isolation.py`'s own docstring.

## Lot 11b acceptance (per `docs/refactoring-plan.md` §6)

"Cross-tenant tests fail closed; policy-engine errors deny by default, never allow by default" —
both delivered and regression-tested, per Verification above.

## Next

Lot 11c (redaction/audit/human-review): apply configured redaction before storage/logging/external
calls, emit audit evidence for every governed execution, support human review for high-risk
outcomes — depends on this lot's identity/tenant context to know *what* to redact and *for whom*.
