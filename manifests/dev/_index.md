# `manifests/dev/` — Development environment overrides (V4, not yet implemented)

This folder is a stub. No environment-override mechanism exists today — the files under
[`../presets/`](../presets/) (in particular
[`local-hybrid-rag.yaml`](../presets/local-hybrid-rag.yaml)) directly serve as the
development configuration.

**What's planned here, in V4** (see [ROADMAP.md](../../ROADMAP.md), "V4 — Governance"
section): an override file applied on top of a base preset, activated when
`MRAG_ENVIRONMENT=dev` (a variable documented in
[docs/guides/installation.md](../../docs/guides/installation.md)). The goal is to allow,
for example, more verbose logging and no authentication locally, without duplicating an
entire production manifest.

Until this feature exists, use a preset from [`../presets/`](../presets/) directly and adapt
it by hand if needed.
