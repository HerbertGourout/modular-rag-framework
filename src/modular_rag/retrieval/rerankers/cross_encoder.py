from __future__ import annotations

from modular_rag.core.models.query import Query
from modular_rag.core.models.retrieved import RetrievedChunk


class CrossEncoderReranker:
    """Rerank chunks using a sentence-transformers cross-encoder."""

    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self.model_name = model
        self._model: object | None = None

    def name(self) -> str:
        return "cross-encoder"

    def _get_model(self) -> object:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self.model_name)
            except ImportError as exc:
                raise ImportError(
                    "Install 'sentence-transformers' (pip install modular-rag[v1])."
                ) from exc
        return self._model

    def rerank(
        self, query: Query, chunks: list[RetrievedChunk], k: int = 5
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        model = self._get_model()
        pairs = [(query.text, c.chunk.content) for c in chunks]
        scores = model.predict(pairs)  # type: ignore[union-attr]
        ranked = sorted(zip(scores, chunks, strict=True), key=lambda x: x[0], reverse=True)[:k]
        return [
            chunk.model_copy(update={"score": float(score), "rank": i})
            for i, (score, chunk) in enumerate(ranked, 1)
        ]
