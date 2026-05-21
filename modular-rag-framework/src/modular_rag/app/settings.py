from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MRAG_",
        env_file=".env",
        extra="ignore",
    )

    # LLM backends
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2048

    # Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 64

    # Vector store (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "documents"

    # Retrieval
    retrieval_k: int = 20
    reranker_k: int = 5
    vector_weight: float = 0.7
    bm25_weight: float = 0.3

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Security
    security_enabled: bool = False

    # Observability
    telemetry_enabled: bool = True
    otel_endpoint: str = ""
    log_level: str = "INFO"

    # Graph store (V3)
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
