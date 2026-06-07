from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ComponentConfig(BaseModel):
    type: str
    config: dict[str, Any] = Field(default_factory=dict)


class PipelineManifest(BaseModel):
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


@runtime_checkable
class ManifestLoader(Protocol):
    """Load and validate a PipelineManifest from a YAML file."""

    def load(self, path: str) -> PipelineManifest: ...
