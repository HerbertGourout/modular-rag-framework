"""Public application surface for API and CLI entry points."""

from modular_rag.app.bootstrap import load_application
from modular_rag.app.config_resolution import resolve_manifest, validate_capabilities
from modular_rag.app.default_factories import create_default_registry
from modular_rag.contracts.identity import TenantContext, TokenVerifier
from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.core.enums import ReadinessState
from modular_rag.core.errors import (
    AuthenticationError,
    ConfigurationError,
    ModularRAGError,
    SecurityError,
)
from modular_rag.ingestion.pipelines.default import ingest_directory, ingest_path

__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "ModularRAGError",
    "PipelineManifest",
    "ReadinessState",
    "SecurityError",
    "TenantContext",
    "TokenVerifier",
    "create_default_registry",
    "ingest_directory",
    "ingest_path",
    "load_application",
    "resolve_manifest",
    "validate_capabilities",
]
