"""EvoRAG-style graph versioning: apply feedback to reinforce or weaken graph edges (V3)."""
from __future__ import annotations

import structlog

from modular_rag.memory.graph.knowledge_graph import KnowledgeGraph

log = structlog.get_logger(__name__)


class GraphVersionManager:
    """Apply user feedback to update edge weights in a KnowledgeGraph."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph

    def reinforce(self, source_id: str, target_id: str, delta: float = 0.1) -> None:
        for edge in self._graph._edges:
            if edge.source_id == source_id and edge.target_id == target_id:
                edge.weight = min(1.0, edge.weight + delta)
                log.debug("graph.reinforce", src=source_id, tgt=target_id, weight=edge.weight)
                return

    def weaken(self, source_id: str, target_id: str, delta: float = 0.1) -> None:
        for edge in self._graph._edges:
            if edge.source_id == source_id and edge.target_id == target_id:
                edge.weight = max(0.0, edge.weight - delta)
                log.debug("graph.weaken", src=source_id, tgt=target_id, weight=edge.weight)
                return

    def prune(self, min_weight: float = 0.1) -> int:
        before = len(self._graph._edges)
        self._graph._edges = [e for e in self._graph._edges if e.weight >= min_weight]
        pruned = before - len(self._graph._edges)
        log.info("graph.pruned", pruned=pruned)
        return pruned
