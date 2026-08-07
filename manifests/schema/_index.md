# `manifests/schema/` — generated JSON Schema

`pipeline-manifest.schema.json` is a **generated artifact**, not hand-maintained — it's the
literal output of `PipelineManifest.model_json_schema()` (`src/modular_rag/contracts/manifests.py`).

Regenerate it after any change to `PipelineManifest` or its nested sections
(`GovernanceSection`, `QualitySection`, `ObservabilitySection`, `LifecycleSection`,
`EngineSelection`, `ComponentConfig`):

```bash
mrag manifest-schema > manifests/schema/pipeline-manifest.schema.json
```

If this file and `mrag manifest-schema`'s live output ever diverge, the file is stale — trust
the live command, not the checked-in copy, and regenerate.
