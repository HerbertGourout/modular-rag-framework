from __future__ import annotations

from pydantic import BaseModel

from modular_rag.core.enums import RetrievalMethod
from modular_rag.core.models.chunk import Chunk


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float
    rank: int
    retrieval_method: RetrievalMethod = RetrievalMethod.HYBRID

    model_config = {"frozen": True}

    def __lt__(self, other: RetrievedChunk) -> bool:
        return self.rank < other.rank
