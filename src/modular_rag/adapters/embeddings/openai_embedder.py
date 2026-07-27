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
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._batch_size = batch_size
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
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS.get(self._model, 1536)

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

        async_client = openai.AsyncOpenAI(api_key=self._api_key)
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            response = await async_client.embeddings.create(input=batch, model=self._model)
            all_embeddings.extend([item.embedding for item in response.data])
        return all_embeddings
