# `manifests/staging/` — Pre-production environment overrides (V4, not yet implemented)

This folder is a stub, same as [`../dev/`](../dev/) and [`../production/`](../production/).
No environment-override mechanism is implemented yet — see
[ROADMAP.md](../../ROADMAP.md), "V4 — Governance" section.

**What's planned here**: a configuration that mirrors production (same security guards,
same models) but points to test resources — a dedicated Qdrant cluster, an API key with a
limited quota, a demo tenant isolated from real client data. The goal is to validate a
manifest or policy change under near-real conditions before promoting it to production,
without risking sensitive data.

In the meantime, manually derive a manifest from
[`secure-enterprise-rag.yaml`](../presets/secure-enterprise-rag.yaml) — since Étape 7 (ADR-0007)
this preset is Runnable, not Blueprint (see [`../README.md`](../README.md)): governance section
with tenant isolation/redaction/inline policy engine/Postgres audit, `${QDRANT_URL}`/
`secret://QDRANT_API_KEY`/`secret://AUDIT_DATABASE_URL` actually resolved by
`app/config_resolution.py::resolve_manifest()`. Copying it as a staging base is safe; just set
the referenced environment variables for the staging environment.
