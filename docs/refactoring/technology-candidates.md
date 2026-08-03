# Technology Candidates — Parking Lot

**Status:** none of these are approved architecture decisions. This is a holding area, not part
of the committed plan. It exists so a compatibility review done against a broader infrastructure
stack doesn't get lost, without forcing 15+ new named dependencies into
[docs/refactoring-plan.md](../refactoring-plan.md) before they're actually needed.

**Promotion rule:** when the target lot's owner is about to start it, they re-confirm the
candidate below still makes sense (nothing gone stale, nothing superseded), then write the
decision directly into the lot's description in `docs/refactoring-plan.md` §5 and delete the row
here. This file is never itself a source of truth once that happens.

**Two things currently gate most of these:**
1. [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) is still `Proposed`, not
   `Accepted`.
2. Target deployment platform and topology is an explicitly open question
   (`docs/refactoring-plan.md` §10) — several rows below depend on it.

---

## Candidates

| Domain | Candidate | Rationale | Gated on | Target lot |
|---|---|---|---|---|
| Policy | OPA | Open item since ADR-0003; one policy engine is enough at this team size | ADR-0005 accepted | 11b |
| Secrets | OpenBao | Secret-reference resolution needed by the manifest v2 schema | — | 9 |
| Observability | OpenTelemetry + Prometheus + Grafana Loki + Grafana Tempo | `TraceStep` should emit OTel-compatible spans instead of a proprietary format | — | 10 |
| LLM observability | Langfuse (self-hosted) | Ready-made sink for the audit trail instead of a hand-built event store | deployment topology | 10 |
| Evaluation | Ragas + DeepEval + Promptfoo | Fixes `ExactMatchEvaluator`'s actual behavior by wrapping a maintained library under `MetricsProtocol`, instead of hand-rolled metric code | — | 13 |
| Supply-chain | Cosign, Syft, Grype, Trivy | Lightweight (CLI/GitHub Actions, no infra to run); matches the SBOM/vuln/licence gate already scoped | — | 16b |
| Model gateway | LiteLLM Proxy | Avoids hand-rolled multi-LLM routing logic in `adapters/llms/` | V2 scope opens (`adapters/llms/` is currently a reserved namespace) | V2 |
| Agent runtime | LangGraph (or the Lot 6 spike winner) behind the `DocumentEngine` port | Never expose the engine's own API as the platform contract | Lot 6 spike outcome | 6, 7 |
| Search | OpenSearch | Only if in-memory BM25 becomes a real bottleneck at scale | evidence of an actual scale problem | 12b |
| MLOps | MLflow | If V3.2 (continuous fine-tuning) is ever built, this is the external tool to delegate to, not something to build | V3.2 in scope | V3.2 (deferred) |
| Data quality | Great Expectations or Soda Core | Validates manifest schemas and golden-dataset structure instead of hand-rolled checks | — | 9, 13 |
| Catalogue | OpenMetadata | Backend candidate for the V1.2 data-lineage tracker (source → processing → response) instead of building one from scratch | — | audit / V1.2 |
| Backup | Velero + Restic/Kopia | Matches the restore-proof requirement in 12c and the runbooks in 16c, if the deployment target is Kubernetes | deployment topology = Kubernetes | 12c, 16c |
| API Gateway | Envoy Gateway or Kong | Could absorb rate-limiting/TLS/auth-termination in front of the service, reducing what 16a has to build in-app | deployment topology decision | 16a |
| GitOps | Argo CD | One deployment option for 16c, not a package dependency | deployment topology decision | 16c |
| Streaming | Kafka — **as an audit-sink option only**, never an internal backbone | Relevant only for SIEM-scale audit export in deployments that already run Kafka | deployment topology decision | 10 |
| Data orchestration | Dagster or Airflow — **deployer-side, not a package dependency** | Triggers the periodic jobs the package already exposes as idempotent commands (reconciliation, compliance reports, drift detection) | deployment topology decision | 12b |
| Object storage | Ceph, via its S3-compatible gateway | One possible S3-compatible backend among others, if the storage adapter targets a generic S3 interface | storage-adapter design | document/artifact storage |
| Registry | Harbor | Optional private container registry; GitHub Container Registry is already available via the existing GitHub Actions setup | deployment topology decision | 16b |

## Explicitly rejected (not parked — closed)

These were considered and dropped, not deferred. Re-raising them requires new evidence, not just
revisiting this list:

- **Multi-agent: a bespoke in-house orchestration runtime** — contradicts
  [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) §5.2, which delegates generic
  multi-agent orchestration to the selected external engine.
- **CI/CD: GitLab CE, Forgejo, Tekton** — contradicts the GitHub Actions migration already
  completed (commit `47ea77f`).
- **Ingestion platforms (NiFi, Camel), distributed processing (Flink, Spark), durable workflow
  engines as a direct dependency (Temporal), geospatial (PostGIS, GeoMesa), lakehouse formats
  (Iceberg, Delta Lake, Hudi), model serving infrastructure (KServe, vLLM — subsumed by the
  LiteLLM gateway choice above), machine identity (SPIFFE/SPIRE), service mesh (Istio, Cilium),
  Kubernetes distribution/bare-metal/virtualization choices** — these describe an
  organization-wide infrastructure platform layer that this package consumes (if at all) but
  never owns, builds, or selects.
