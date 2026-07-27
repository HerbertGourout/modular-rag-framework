from __future__ import annotations

from enum import StrEnum

import structlog

log = structlog.get_logger(__name__)


class PipelineState(StrEnum):
    IDLE = "idle"
    GUARDING_QUERY = "guarding_query"
    RETRIEVING = "retrieving"
    RERANKING = "reranking"
    GENERATING = "generating"
    GUARDING_ANSWER = "guarding_answer"
    EVALUATING = "evaluating"
    DONE = "done"
    ERROR = "error"


class PipelineStateMachine:
    """Track state transitions through a RAG pipeline execution."""

    _TRANSITIONS: dict[PipelineState, list[PipelineState]] = {
        PipelineState.IDLE: [PipelineState.GUARDING_QUERY, PipelineState.RETRIEVING],
        PipelineState.GUARDING_QUERY: [PipelineState.RETRIEVING, PipelineState.ERROR],
        PipelineState.RETRIEVING: [
            PipelineState.RERANKING,
            PipelineState.GENERATING,
            PipelineState.ERROR,
        ],
        PipelineState.RERANKING: [PipelineState.GENERATING, PipelineState.ERROR],
        PipelineState.GENERATING: [
            PipelineState.GUARDING_ANSWER,
            PipelineState.DONE,
            PipelineState.ERROR,
        ],
        PipelineState.GUARDING_ANSWER: [
            PipelineState.EVALUATING,
            PipelineState.DONE,
            PipelineState.ERROR,
        ],
        PipelineState.EVALUATING: [PipelineState.DONE, PipelineState.ERROR],
        PipelineState.DONE: [],
        PipelineState.ERROR: [],
    }

    def __init__(self, pipeline_id: str) -> None:
        self.pipeline_id = pipeline_id
        self.state = PipelineState.IDLE

    def transition(self, to: PipelineState) -> None:
        allowed = self._TRANSITIONS.get(self.state, [])
        if to not in allowed:
            raise ValueError(
                f"[{self.pipeline_id}] Invalid transition {self.state} → {to}. "
                f"Allowed: {allowed}"
            )
        log.debug("state_machine.transition", pipeline=self.pipeline_id, frm=self.state, to=to)
        self.state = to
