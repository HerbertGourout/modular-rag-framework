from __future__ import annotations


class ModularRAGError(Exception):
    """Base exception for all framework errors."""


class ConfigurationError(ModularRAGError):
    """Raised when a manifest or settings value is invalid."""


class RegistryError(ModularRAGError):
    """Raised when a component lookup in the registry fails."""


class IngestionError(ModularRAGError):
    """Raised when document parsing or chunking fails."""


class IndexingError(ModularRAGError):
    """Raised when writing to a vector/lexical store fails."""


class RetrievalError(ModularRAGError):
    """Raised when a retrieval operation fails."""


class GenerationError(ModularRAGError):
    """Raised when an LLM call fails or returns an unusable response."""


class SecurityError(ModularRAGError):
    """Raised when a security guard blocks a query or answer."""


class PolicyViolationError(SecurityError):
    """Raised when a pipeline action violates a declared policy."""


class EvaluationError(ModularRAGError):
    """Raised when scoring or benchmark execution fails."""


class GraphError(ModularRAGError):
    """Raised when graph construction or traversal fails (V3)."""


class AgentError(ModularRAGError):
    """Raised when an agent task fails (V2)."""


class StorageError(ModularRAGError):
    """Raised when a storage backend operation fails."""


class ManifestError(ConfigurationError):
    """Raised when a YAML manifest cannot be loaded or validated."""
