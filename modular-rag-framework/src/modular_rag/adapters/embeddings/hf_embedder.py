"""HuggingFace / sentence-transformers embedding adapter."""
from __future__ import annotations

from typing import Any


class HuggingFaceEmbedder:
    """Uses sentence-transformers locally (no API key required).

    Default model: BAAI/bge-small-en-v1.5 (384-dim, ~130 MB, strong English).
    """

    def __init__(
        self,
        model: str = "BAAI/bge-small-en-v1.5",
        batch_size: int = 32,
        device: str = "cpu",
    ) -> None:
        self._model_name = model
        self._batch_size = batch_size
        self._device = device
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers is required for HuggingFaceEmbedder. "
                    "Install it with: pip install modular-rag[v1]"
                ) from exc
            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    @property
    def dimensions(self) -> int:
        model = self._get_model()
        return model.get_sentence_embedding_dimension()

    def name(self) -> str:
        return f"hf-{self._model_name.split('/')[-1]}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [e.tolist() for e in embeddings]

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, texts)
