# Documentation — Modular RAG Framework

This documentation is organized by intent rather than by technical folder: before looking
for a specific file, ask yourself *why* you're looking, not *where*. The table below points
you toward the right document based on your profile and your current need.

**New to this project, or not sure where to start?** Read
[onboarding.md](onboarding.md) first — it is the repository's entry point. It gives the five-step
path from "what is this?" to a first contribution, explains who should read what (developer, tech
lead, delivery consultant, functional profile, security/compliance), says which documents are
authoritative, and walks through the full V1 → V5 journey in plain language.

---

## By intent

| You want to... | Go to |
|---|---|
| Join the project and know what to read, in order | [onboarding.md](onboarding.md) |
| Understand what the framework can do, without technical jargon | [onboarding.md](onboarding.md), section 3 |
| Read a deeper product and architecture overview, by role | [guides/framework-overview-onboarding.md](guides/framework-overview-onboarding.md) |
| Write or restructure documentation | [guides/documentation-style-guide.md](guides/documentation-style-guide.md) |
| Track the developer-onboarding documentation overhaul | [onboarding-overhaul-plan.md](onboarding-overhaul-plan.md) |
| Evaluate the product hypothesis and evidence needed before commercial claims | [business-case.md](business-case.md) |
| See what's delivered vs. planned, version by version | [../ROADMAP.md](../ROADMAP.md) |
| Track the engine-agnostic refactoring programme | [refactoring-plan.md](refactoring-plan.md) |
| Run the framework for the first time | [guides/getting-started.md](guides/getting-started.md) |
| Install dependencies and configure the environment | [guides/installation.md](guides/installation.md) |
| Understand the architecture in depth (layers, contracts, data flow) | [architecture/_index.md](architecture/_index.md) |
| Understand why a structural decision was made | [adr/_index.md](adr/_index.md) |
| Add a new component (chunker, retriever, generator...) | [guides/plugin-development.md](guides/plugin-development.md) |
| Deploy to production | [guides/deployment.md](guides/deployment.md) |
| Read or wire up trace telemetry, live spans or operational metrics | [guides/observability.md](guides/observability.md) |
| Adapt the reference dashboard, alerts, SLOs and runbooks | [observability/README.md](observability/README.md) |
| Use the REST API | [api/_index.md](api/_index.md) |
| Record feedback or run offline drift analysis | [guides/feedback-and-drift.md](guides/feedback-and-drift.md) |
| Understand the accepted L0/L1/L2 assurance direction | [adr/0015-portable-assurance-and-external-application-boundary.md](adr/0015-portable-assurance-and-external-application-boundary.md) |
| Choose a manifest or create a new one | [../manifests/_index.md](../manifests/_index.md) |
| Contribute code (setup, rules, MR checklist) | [../CONTRIBUTING.md](../CONTRIBUTING.md) |
| Look up a term (RRF, ULID, groundedness, EvoRAG...) | [glossary.md](glossary.md) |
| Fix a common error (Qdrant unreachable, RegistryError, layering violation...) | [guides/troubleshooting.md](guides/troubleshooting.md) |

## Folder structure

```
docs/
├── onboarding.md       ← Entry point: reading path, functional profiles, full journey
├── business-case.md    ← Business case (management, delivery, commercial)
├── adr/                ← Accepted and proposed architecture decisions, with status and consequences
├── api/                ← REST API reference
├── architecture/        ← Complete technical specification (layers, models, flows, security)
├── guides/              ← Practical, task-oriented guides (installation, deployment, plugins...)
├── observability/       ← Reference dashboard, alerts, SLOs and runbooks
├── glossary.md          ← Definitions of recurring terms (RRF, ULID, groundedness, EvoRAG...)
└── archive/             ← Superseded or low-ongoing-utility documents, kept for the record —
                            see archive/README.md for what's there and why
```

Each subfolder has its own `_index.md` with a finer-grained breakdown of its content.
