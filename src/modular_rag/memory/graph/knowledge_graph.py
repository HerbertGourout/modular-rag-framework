"""In-memory knowledge graph data model (V3). Despite the module's original docstring, this
is a plain Python dict/list implementation — it never actually imported or depended on
`networkx` (the `v3` optional-dependency group's declared `networkx>=3.3` is unused by this
file; corrected here, not removed from `pyproject.toml`, since that's a separate question from
this docstring's own accuracy).

Retained, not removed, in Lot 17 (docs/refactoring-plan.md) — with a caveat recorded
honestly: `neighbours()`/`subgraph_for_query()` are genuine multi-hop-traversal/sub-graph-
selection logic, which is exactly the GraphRAG capability ADR-0005 §5.2
(docs/adr/0005-document-ai-control-plane-boundary.md) delegates to the selected external
engine, not a passive data model. `docs/architecture/structure.md`'s own note hedges this as
"contingent on Lot 6 evidence, not decided yet" — Lot 6 (the LangGraph/LlamaIndex Workflows
spike, ADR-0006) never actually produced evidence bearing on this specific question, so it
remains genuinely undecided, not resolved by this lot. This file differs from the agent/
routing/planning cluster removed alongside it in one material way: it has real test coverage
(`tests/unit/memory/test_knowledge_graph.py`), so it was not treated as a zero-evidence dead
prototype. Still has zero consumers anywhere outside its own test — it is not wired into any
retriever or pipeline today."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from modular_rag.core.enums import GraphRelation

log = structlog.get_logger(__name__)


@dataclass
class GraphNode:
    id: str
    label: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)
    source_chunk_ids: list[str] = field(default_factory=list)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    relation: GraphRelation
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    """Lightweight in-memory graph — swap with Neo4jGraph adapter in production."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges.append(edge)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def neighbours(self, node_id: str, hops: int = 1) -> list[GraphNode]:
        visited: set[str] = {node_id}
        frontier: set[str] = {node_id}
        for _ in range(hops):
            next_frontier: set[str] = set()
            for edge in self._edges:
                if edge.source_id in frontier and edge.target_id not in visited:
                    next_frontier.add(edge.target_id)
                elif edge.target_id in frontier and edge.source_id not in visited:
                    next_frontier.add(edge.source_id)
            visited |= next_frontier
            frontier = next_frontier
        visited.discard(node_id)
        return [self._nodes[nid] for nid in visited if nid in self._nodes]

    def subgraph_for_query(self, entity_labels: list[str], hops: int = 2) -> list[GraphNode]:
        seeds = [n for n in self._nodes.values() if n.label in entity_labels]
        result: set[str] = {n.id for n in seeds}
        for seed in seeds:
            for neighbour in self.neighbours(seed.id, hops=hops):
                result.add(neighbour.id)
        return [self._nodes[nid] for nid in result]

    def stats(self) -> dict[str, int]:
        return {"nodes": len(self._nodes), "edges": len(self._edges)}
