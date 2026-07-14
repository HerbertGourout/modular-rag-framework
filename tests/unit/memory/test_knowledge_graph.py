"""Unit tests for KnowledgeGraph."""
from __future__ import annotations

from modular_rag.core.enums import GraphRelation
from modular_rag.core.ids import new_id
from modular_rag.memory.graph.knowledge_graph import GraphEdge, GraphNode, KnowledgeGraph


def _node(label: str, type_: str = "ENTITY") -> GraphNode:
    return GraphNode(id=new_id(), label=label, type=type_)


def test_add_and_get_node():
    kg = KnowledgeGraph()
    node = _node("Paris")
    kg.add_node(node)
    assert kg.get_node(node.id) is node


def test_get_nonexistent_node_returns_none():
    kg = KnowledgeGraph()
    assert kg.get_node("nonexistent") is None


def test_add_edge_and_neighbours():
    kg = KnowledgeGraph()
    paris = _node("Paris", "CITY")
    france = _node("France", "COUNTRY")
    kg.add_node(paris)
    kg.add_node(france)
    edge = GraphEdge(
        source_id=paris.id,
        target_id=france.id,
        relation=GraphRelation.IS_PART_OF,
    )
    kg.add_edge(edge)
    neighbours = kg.neighbours(paris.id, hops=1)
    assert france.id in [n.id for n in neighbours]


def test_neighbours_hops():
    kg = KnowledgeGraph()
    a = _node("A")
    b = _node("B")
    c = _node("C")
    kg.add_node(a)
    kg.add_node(b)
    kg.add_node(c)
    kg.add_edge(GraphEdge(source_id=a.id, target_id=b.id, relation=GraphRelation.CAUSES))
    kg.add_edge(GraphEdge(source_id=b.id, target_id=c.id, relation=GraphRelation.CAUSES))

    one_hop = kg.neighbours(a.id, hops=1)
    two_hop = kg.neighbours(a.id, hops=2)
    assert len(two_hop) >= len(one_hop)


def test_stats():
    kg = KnowledgeGraph()
    a = _node("X")
    b = _node("Y")
    kg.add_node(a)
    kg.add_node(b)
    kg.add_edge(GraphEdge(source_id=a.id, target_id=b.id, relation=GraphRelation.DEPENDS_ON))
    stats = kg.stats()
    assert stats["nodes"] == 2
    assert stats["edges"] == 1


def test_subgraph_for_query():
    kg = KnowledgeGraph()
    rag = _node("RAG", "CONCEPT")
    retrieval = _node("Retrieval", "CONCEPT")
    kg.add_node(rag)
    kg.add_node(retrieval)
    kg.add_edge(
        GraphEdge(source_id=rag.id, target_id=retrieval.id, relation=GraphRelation.DEPENDS_ON)
    )

    subgraph = kg.subgraph_for_query(["RAG"], hops=1)
    node_labels = [n.label for n in subgraph]
    assert "RAG" in node_labels
