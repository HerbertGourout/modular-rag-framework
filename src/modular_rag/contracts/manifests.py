from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_SCHEMA_VERSIONS = ("1.0", "2.0")


class ComponentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    config: dict[str, Any] = Field(default_factory=dict)


class EngineSelection(BaseModel):
    """Which `DocumentEngine` adapter (Lot 7/8) wires this pipeline. Optional —
    a manifest without this section defaults to the native adapter
    (`RAGEngine`), preserving v1 behavior exactly. Populating it is one of
    the markers of a v2 manifest (`app/manifest_migration.py`)."""

    model_config = ConfigDict(extra="forbid")

    adapter: str = "native"  # "native" | "langgraph" (Lot 15) | ...
    config: dict[str, Any] = Field(default_factory=dict)


class GovernanceSection(BaseModel):
    """Governance components activated by the application composition root.

    `tenant_enforcement` is a deliberate, explicit governance *intent* flag —
    separate from `tenant_policy` (which component implements it). Defaulting
    to `False` makes "no tenant isolation" a visible, auditable fact on every
    migrated/loaded manifest instead of a silent absence (ADR-0007 §3: "a
    declared manifest section that cannot be activated must fail validation").
    `tenant_enforcement=True` with `tenant_policy=None` is a validation error
    (see `app/config_resolution.py::validate_capabilities`), not a silent
    no-op.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_enforcement: bool = False
    tenant_policy: ComponentConfig | None = None
    policy_engine: ComponentConfig | None = None
    redactor: ComponentConfig | None = None
    review_queue: ComponentConfig | None = None
    audit_sink: ComponentConfig | None = None


class QualitySection(BaseModel):
    """Evaluation profile and an optional wired quality gate."""

    model_config = ConfigDict(extra="forbid")

    eval_profile: str | None = None
    gate: ComponentConfig | None = None


class ObservabilitySection(BaseModel):
    """Telemetry and tracing components selected for runtime observability.

    `telemetry` records a post-hoc `Trace`/`Metrics` summary after a run
    completes. `tracer` (ADR-0012) creates live OpenTelemetry-compatible
    spans as a run executes — a deliberately separate, both-optional
    mechanism; a pipeline may configure either, both, or neither.
    """

    model_config = ConfigDict(extra="forbid")

    telemetry: ComponentConfig | None = None
    tracer: ComponentConfig | None = None


class LifecycleSection(BaseModel):
    """Document identity, idempotency and deletion ledger."""

    model_config = ConfigDict(extra="forbid")

    ledger: ComponentConfig | None = None


class PipelineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    id: str
    description: str = ""
    tenant: str = "default"
    environment: str = "dev"

    chunker: ComponentConfig = ComponentConfig(type="adaptive")
    embedder: ComponentConfig = ComponentConfig(type="sentence-transformers")
    indexer: ComponentConfig = ComponentConfig(type="qdrant")
    retriever: ComponentConfig = ComponentConfig(type="hybrid")
    reranker: ComponentConfig | None = None
    generator: ComponentConfig = ComponentConfig(type="openai")
    security: ComponentConfig | None = None
    evaluation: ComponentConfig | None = None

    # Engine-independent control-plane sections (ADR-0005/ADR-0007).
    engine: EngineSelection | None = None
    governance: GovernanceSection | None = None
    quality: QualitySection | None = None
    observability: ObservabilitySection | None = None
    lifecycle: LifecycleSection | None = None


@runtime_checkable
class ManifestLoader(Protocol):
    """Load and validate a PipelineManifest from a YAML file."""

    def load(self, path: str) -> PipelineManifest: ...
