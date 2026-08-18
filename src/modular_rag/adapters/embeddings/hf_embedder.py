"""HuggingFace / sentence-transformers embedding adapter."""
from __future__ import annotations

from typing import Any


class HuggingFaceEmbedder:
    """Uses sentence-transformers locally (no API key required).

    Default model: BAAI/bge-small-en-v1.5 (384-dim, ~130 MB, strong English).
    """

    # ADR-0009 (docs/adr/0009-vector-indexer-dimension-reconciliation.md):
    # `.dimensions` used to unconditionally call `_get_model()`, forcing a
    # real sentence-transformers download/load — fine when embedding text
    # anyway, but a `VectorIndexer` (e.g. `QdrantStore`) now reads
    # `.dimensions` to reconcile its collection's vector size, and could
    # otherwise force a model load merely because a pipeline was wired or a
    # store opened its first connection, not because anything actually
    # needed to embed text yet (architecture-reviewer finding, breaks
    # CLAUDE.md §05.7's lazy-import invariant). Known models' dimensions are
    # fixed, publicly documented facts about released model architectures,
    # not something that changes — a static table keeps `.dimensions` free
    # for every model this repository's own presets actually use; an
    # unrecognized model name still falls back to loading it for real, since
    # there is no way to know an arbitrary model's output size without it —
    # ADR-0009 defers exactly that fallback's cost to the store's own first
    # real use (see `QdrantStore._get_client()`), not wiring time.
    _DIMENSIONS = {
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-base-en-v1.5": 768,
        "BAAI/bge-large-en-v1.5": 1024,
        "sentence-transformers/all-MiniLM-L6-v2": 384,
    }

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
        known = self._DIMENSIONS.get(self._model_name)
        if known is not None:
            return known
        model = self._get_model()
        return int(model.get_sentence_embedding_dimension())

    def known_dimensions(self) -> int | None:
        """Codex review HIGH-002 (Lot 6, fifth pass): a cheap-only variant
        of `.dimensions` that never calls `_get_model()` — returns `None`
        rather than downloading/loading a model for a name outside
        `_DIMENSIONS`'s static table. `QdrantStore.check_health()` duck-types
        this (`getattr(embedder, "known_dimensions", None)`) so a readiness
        probe can never reach the loading branch `.dimensions` itself still
        has for real `generate()`/`embed()` use — a probe against a custom,
        unrecognized model name previously had no timeout, no lock against
        concurrent probes each starting their own redundant download, and
        could block pod startup entirely on a slow/unavailable model
        registry even though Qdrant itself was healthy."""
        return self._DIMENSIONS.get(self._model_name)

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
