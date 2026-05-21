# Module Model — Layer Boundaries

## Dependency rule

```
adapters/ → contracts/ + core/models/
domain modules (ingestion, retrieval, generation, agents, security, memory, eval) → contracts/ + core/models/
orchestration/ → contracts/ + core/models/ + app/
app/ → orchestration/ + contracts/ + core/
cli/ + api/ → app/ only
```

**Forbidden**: any domain module importing from another domain module directly.

## `app/` vs `orchestration/` boundary

| Module | Role |
|---|---|
| `app/settings.py` | Environment config (pydantic-settings, env vars) |
| `app/container.py` | Dependency injection: holds wired component instances |
| `app/bootstrap.py` | Load manifest → wire container → return RAGEngine |
| `app/lifecycle.py` | Startup / shutdown hooks |
| `orchestration/engine.py` | Main runtime: ingest, answer, retrieve |
| `orchestration/registry.py` | Maps type names → factory callables |
| `orchestration/router.py` | Classify query → RoutingStrategy |
| `orchestration/flow_compiler.py` | RoutingStrategy → ExecutionPlan |
| `orchestration/state_machine.py` | Track pipeline state transitions |

`app/` is process-level wiring. `orchestration/` is runtime logic.

## `security/` sub-package boundary

| Sub-package | Concern |
|---|---|
| `security/filters/` | Safety: query/answer inspection (injection, flooding) |
| `security/detectors/` | Safety: adversarial patterns (exfiltration, poisoning) |
| `security/redaction/` | Safety: PII and secret masking in text |
| `security/policies/` | Security: RBAC, tenant isolation, policy enforcement (V4) |
