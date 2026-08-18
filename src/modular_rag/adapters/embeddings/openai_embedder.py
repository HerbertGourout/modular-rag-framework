"""OpenAI embedding adapter — implements the Embedder contract."""
from __future__ import annotations

from typing import Any


class OpenAIEmbedder:
    """Uses the OpenAI Embeddings API (text-embedding-3-small by default)."""

    _DIMENSIONS = {
        "text-embedding-ada-002": 1536,
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        batch_size: int = 64,
        timeout: float = 30.0,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._batch_size = batch_size
        self._timeout = timeout
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise ImportError(
                    "openai is required for OpenAIEmbedder. "
                    "Install it with: pip install modular-rag[v1]"
                ) from exc
            self._client = openai.OpenAI(api_key=self._api_key, timeout=self._timeout)
        return self._client

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS.get(self._model, 1536)

    def known_dimensions(self) -> int | None:
        """Codex review HIGH-002 (Lot 6, fifth pass): see
        `HuggingFaceEmbedder.known_dimensions()` for the full rationale —
        always cheap here already (a static dict lookup, no network call
        either way), but implemented for the same duck-typed contract
        `QdrantStore.check_health()` relies on."""
        return self.dimensions

    def name(self) -> str:
        return f"openai-{self._model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            response = client.embeddings.create(input=batch, model=self._model)
            all_embeddings.extend([item.embedding for item in response.data])
        return all_embeddings

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai is required for OpenAIEmbedder. "
                "Install it with: pip install modular-rag[v1]"
            ) from exc

        async_client = openai.AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)
        try:
            all_embeddings: list[list[float]] = []
            for i in range(0, len(texts), self._batch_size):
                batch = texts[i : i + self._batch_size]
                response = await async_client.embeddings.create(input=batch, model=self._model)
                all_embeddings.extend([item.embedding for item in response.data])
            return all_embeddings
        finally:
            await async_client.close()

    def close(self) -> None:
        """Release the underlying sync openai client, if one was ever opened
        (Lot 14, docs/refactoring-plan.md — "own and close clients/
        resources"). `aembed()` opens and closes its own per-call async
        client already — nothing persistent there to release."""
        if self._client is not None:
            self._client.close()
            self._client = None
