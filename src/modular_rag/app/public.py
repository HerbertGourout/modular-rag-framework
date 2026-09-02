"""Public application surface for API and CLI entry points."""

from modular_rag.app.bootstrap import load_application
from modular_rag.app.config_resolution import resolve_manifest, validate_capabilities
from modular_rag.app.default_factories import create_default_registry
from modular_rag.app.postgres_admin import (
    count_expired_audit_events,
    count_expired_feedback,
    count_expired_review_items,
    list_pending_review_items,
    migration_status,
    purge_expired_audit_events,
    purge_expired_feedback,
    purge_expired_review_items,
    resolve_review_item,
    rollback_migrations,
    run_migrations,
)
from modular_rag.contracts.feedback import Feedback, FeedbackRating
from modular_rag.contracts.identity import TenantContext, TokenVerifier
from modular_rag.contracts.manifests import PipelineManifest
from modular_rag.contracts.reconciliation import ReconciliationReport, RepairResult
from modular_rag.contracts.tracing import Tracer
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
    "Feedback",
    "FeedbackRating",
    "ModularRAGError",
    "PipelineManifest",
    "ReadinessState",
    "ReconciliationReport",
    "RepairResult",
    "SecurityError",
    "TenantContext",
    "TokenVerifier",
    "Tracer",
    "count_expired_audit_events",
    "count_expired_feedback",
    "count_expired_review_items",
    "create_default_registry",
    "ingest_directory",
    "ingest_path",
    "list_pending_review_items",
    "load_application",
    "migration_status",
    "purge_expired_audit_events",
    "purge_expired_feedback",
    "purge_expired_review_items",
    "resolve_manifest",
    "resolve_review_item",
    "rollback_migrations",
    "run_migrations",
    "validate_capabilities",
]
