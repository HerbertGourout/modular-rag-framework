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
[`secure-enterprise-rag.yaml`](../presets/secure-enterprise-rag.yaml), pointing it at your
pre-production resources.
