"""A standalone LangGraph application standing in for a client's existing one.

Lot 22 demonstration pilot (ADR-0018 §13). It owns its graph, state and prompts
and imports nothing from `modular_rag`: the framework reaches it only through
the hooks this application chose to expose. Two hooks exist, and both are
*blocking* — an exception raised inside one stops the graph, which is what lets
the adapter claim `ENFORCED` for them. There is no streaming, no tool use and no
hook after the model call.

This is a demonstration pilot, not a pilot in the sense of Lot 22's acceptance
evidence: it is deterministic and synthetic, so it proves the adapter against a
real LangGraph graph, never against a client's production behaviour.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig

Hooks = Mapping[str, Callable[..., None]]

DEFAULT_CORPUS: tuple[dict[str, str], ...] = (
    {
        "id": "a1",
        "tenant_id": "tenant-a",
        "text": "alpha onboarding policy",
        "source": "kb://a",
    },
    {
        "id": "b1",
        "tenant_id": "tenant-b",
        "text": "tenant-b confidential pricing",
        "source": "kb://b",
    },
)


class _State(TypedDict):
    question: str
    tenant: str
    documents: list[dict[str, str]]
    answer: str


class ExistingGraphApp:
    """The client application: retrieve, then generate."""

    application_name = "existing-graph-app"
    application_version = "0.1.0"
    # Hook name -> True when the hook can stop the graph, False when it only observes.
    hook_surface: Mapping[str, bool] = {"retrieval_result": True, "pre_model_egress": True}
    # Model call name -> True when that call is routed through `pre_model_egress`.
    model_paths: Mapping[str, bool] = {"completion": True}
    tool_names: tuple[str, ...] = ()
    streams = False

    def __init__(
        self,
        corpus: tuple[dict[str, str], ...] = DEFAULT_CORPUS,
        *,
        tenant_aware: bool = True,
    ) -> None:
        self._corpus = corpus
        self._tenant_aware = tenant_aware
        self._graph: Any = None

    def invoke(self, text: str, tenant: str, hooks: Hooks) -> dict[str, Any]:
        result = self._compiled().invoke(
            {"question": text, "tenant": tenant, "documents": [], "answer": ""},
            config={"configurable": {"hooks": hooks}},
        )
        return {
            "text": result["answer"],
            "documents": result["documents"],
            # Deliberately claims a tenant: the adapter must keep it inert.
            "metadata": {"tenant_id": "app-claimed-tenant", "model": "demo-model"},
        }

    def _compiled(self) -> Any:
        if self._graph is None:
            from langgraph.graph import END, START, StateGraph

            graph = StateGraph(_State)
            graph.add_node("retrieve", self._retrieve)
            graph.add_node("generate", self._generate)
            graph.add_edge(START, "retrieve")
            graph.add_edge("retrieve", "generate")
            graph.add_edge("generate", END)
            self._graph = graph.compile()
        return self._graph

    def _retrieve(self, state: _State, config: RunnableConfig) -> dict[str, Any]:
        documents = [
            dict(doc)
            for doc in self._corpus
            if not self._tenant_aware or doc["tenant_id"] == state["tenant"]
        ]
        _hook(config, "retrieval_result")(documents)
        return {"documents": documents}

    def _generate(self, state: _State, config: RunnableConfig) -> dict[str, Any]:
        for name in self.model_paths:
            if self.model_paths[name]:
                _hook(config, "pre_model_egress")(name)
        return {"answer": " | ".join(doc["text"] for doc in state["documents"])}


def _hook(config: RunnableConfig, name: str) -> Callable[..., None]:
    hooks: Hooks = config.get("configurable", {}).get("hooks", {})
    return hooks.get(name, lambda *_args: None)


def build_app() -> ExistingGraphApp:
    """Factory the adapter's `engine.config.application` points at."""
    return ExistingGraphApp()
