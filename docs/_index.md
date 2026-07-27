# Documentation — Modular RAG Framework

This documentation is organized by intent rather than by technical folder: before looking
for a specific file, ask yourself *why* you're looking, not *where*. The table below points
you toward the right document based on your profile and your current need.

**New to this project, or not sure where to start?** Read
[onboarding.md](onboarding.md) first — it explains who should read what (developer, tech
lead, delivery consultant, functional profile, security/compliance) and walks through the
full V1 → V5 journey in plain language.

---

## By intent

| You want to... | Go to |
|---|---|
| Understand what the framework can do, without technical jargon | [onboarding.md](onboarding.md), section 3 |
| Understand why this framework exists, to convince a client or a manager | [business-case.md](business-case.md) |
| See what's delivered vs. planned, version by version | [../ROADMAP.md](../ROADMAP.md) |
| Run the framework for the first time | [guides/getting-started.md](guides/getting-started.md) |
| Install dependencies and configure the environment | [guides/installation.md](guides/installation.md) |
| Understand the architecture in depth (layers, contracts, data flow) | [architecture/_index.md](architecture/_index.md) |
| Understand why a structural decision was made | [adr/_index.md](adr/_index.md) |
| Add a new component (chunker, retriever, generator...) | [guides/plugin-development.md](guides/plugin-development.md) |
| Deploy to production | [guides/deployment.md](guides/deployment.md) |
| Read or wire up telemetry / traces | [guides/observability.md](guides/observability.md) |
| Use the REST API | [api/_index.md](api/_index.md) |
| Choose a manifest or create a new one | [../manifests/_index.md](../manifests/_index.md) |
| Contribute code (setup, rules, MR checklist) | [../CONTRIBUTING.md](../CONTRIBUTING.md) |
| Look up a term (RRF, ULID, groundedness, EvoRAG...) | [glossary.md](glossary.md) |
| Fix a common error (Qdrant unreachable, RegistryError, layering violation...) | [guides/troubleshooting.md](guides/troubleshooting.md) |

## Folder structure

```
docs/
├── onboarding.md       ← Entry point: functional profiles + full journey
├── business-case.md    ← Business case (management, delivery, commercial)
├── adr/                ← Settled architecture decisions, with context and consequences
├── api/                ← REST API reference
├── architecture/        ← Complete technical specification (layers, models, flows, security)
├── guides/              ← Practical, task-oriented guides (installation, deployment, plugins...)
├── glossary.md          ← Definitions of recurring terms (RRF, ULID, groundedness, EvoRAG...)
└── reviews/             ← Historical project reviews (context behind past decisions)
```

Each subfolder has its own `_index.md` with a finer-grained breakdown of its content.
