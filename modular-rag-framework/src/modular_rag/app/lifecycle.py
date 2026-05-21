from __future__ import annotations

import structlog

from modular_rag.app.container import Container

log = structlog.get_logger(__name__)


def startup(container: Container) -> None:
    """Run startup hooks for all registered components."""
    log.info("pipeline.startup", pipeline_id=container.manifest.id)


def shutdown(container: Container) -> None:
    """Run graceful shutdown hooks."""
    log.info("pipeline.shutdown", pipeline_id=container.manifest.id)
