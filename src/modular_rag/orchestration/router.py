from __future__ import annotations

import structlog

from modular_rag.core.enums import RoutingStrategy
from modular_rag.core.models.query import Query

log = structlog.get_logger(__name__)

_AGENTIC_KEYWORDS = frozenset(
    ["compare", "analyze", "analyse", "explain why", "multi-step", "reason", "step by step"]
)
_GRAPH_KEYWORDS = frozenset(
    ["relationship", "link", "path", "chain", "how does", "influence", "cascade"]
)


class QueryRouter:
    """Classify a query to select the optimal execution strategy (V2 adaptive routing)."""

    def __init__(
        self,
        force_strategy: RoutingStrategy | None = None,
    ) -> None:
        self._force = force_strategy

    def route(self, query: Query) -> RoutingStrategy:
        if self._force:
            return self._force
        if query.routing_hint:
            return query.routing_hint

        text = query.text.lower()

        if any(kw in text for kw in _GRAPH_KEYWORDS):
            strategy = RoutingStrategy.GRAPH_RAG
        elif any(kw in text for kw in _AGENTIC_KEYWORDS) or len(text.split()) > 40:
            strategy = RoutingStrategy.AGENTIC_RAG
        elif len(text.split()) < 5:
            strategy = RoutingStrategy.LLM_ONLY
        else:
            strategy = RoutingStrategy.SIMPLE_RAG

        log.debug("router.decision", strategy=strategy, query_id=query.id)
        return strategy
