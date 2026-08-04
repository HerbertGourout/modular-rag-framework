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
    """Declarative governance intent. Schema only as of Lot 9 — actual
    fail-closed enforcement is Lot 11b, redaction/audit wiring is Lot 11c.
    Setting `tenant_enforcement: true` here does not, by itself, enforce
    anything yet."""

    model_config = ConfigDict(extra="forbid")

    tenant_enforcement: bool = False
    policy_refs: list[str] = Field(default_factory=list)


class QualitySection(BaseModel):
    """Declarative quality-gate intent. Schema only as of Lot 9 — gate
    enforcement against these thresholds is Lot 13."""

    model_config = ConfigDict(extra="forbid")

    eval_profile: str | None = None
    gates: dict[str, float] = Field(default_factory=dict)


class ObservabilitySection(BaseModel):
    """Declarative telemetry-sink intent. Schema only as of Lot 9 — actual
    sink wiring (e.g. PostgreSQL-backed audit store) is Lot 10."""

    model_config = ConfigDict(extra="forbid")

    telemetry_sink: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


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

    # V2 — agentic
    planner: ComponentConfig | None = None
    agents: list[ComponentConfig] = Field(default_factory=list)

    # V3 — graph memory
    graph_store: ComponentConfig | None = None

    # V4 — governance
    policies: list[str] = Field(default_factory=list)

    # V5 — multimodal
    modalities: list[str] = Field(default_factory=lambda: ["text"])

    # Schema v2 sections (Lot 9) — see each section's own docstring for what
    # is (and isn't) actually enforced yet. All optional and default to None
    # so every existing v1 manifest keeps validating unchanged.
    engine: EngineSelection | None = None
    governance: GovernanceSection | None = None
    quality: QualitySection | None = None
    observability: ObservabilitySection | None = None


@runtime_checkable
class ManifestLoader(Protocol):
    """Load and validate a PipelineManifest from a YAML file."""

    def load(self, path: str) -> PipelineManifest: ...
