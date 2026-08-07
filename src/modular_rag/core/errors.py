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


class AuthenticationError(SecurityError):
    """Raised when a bearer token fails identity verification (Lot 11b,
    docs/refactoring-plan.md) — invalid signature, expired, wrong audience/
    issuer, or missing required claims. Never caught and downgraded to an
    anonymous/guest identity; verification failure must deny, not degrade."""


class EvaluationError(ModularRAGError):
    """Raised when scoring or benchmark execution fails."""


class StorageError(ModularRAGError):
    """Raised when a storage backend operation fails."""


class ManifestError(ConfigurationError):
    """Raised when a YAML manifest cannot be loaded or validated."""


class EngineError(ModularRAGError):
    """Base error for all DocumentEngine (contracts/engine.py) failures — the
    delegation boundary defined by Lot 7, per ADR-0005 §5.2 / ADR-0006."""


class EngineTimeoutError(EngineError):
    """Raised when a DocumentEngine call exceeds its deadline."""


class EngineCancelledError(EngineError):
    """Raised when a DocumentEngine call is cancelled via its ExecutionContext's
    CancellationToken."""


class EngineCapabilityError(EngineError):
    """Raised when a caller invokes a DocumentEngine method the adapter's
    declared `capabilities` says it does not support (e.g. calling `astream`
    on an engine that doesn't declare EngineCapability.STREAMING)."""
