# Deployment Guide

## Architecture overview

```
                ┌─────────────────────────────────┐
                │   Load Balancer / API Gateway    │
                └───────────────┬─────────────────┘
                                │
                ┌───────────────▼─────────────────┐
                │    FastAPI Application           │
                │    (modular_rag.api)             │
                └──┬────────────────────────┬─────┘
                   │                        │
        ┌──────────▼──────────┐   ┌────────▼────────────┐
        │   Qdrant Vector DB  │   │  LLM API             │
        │   (localhost:6333)  │   │  (OpenAI / Anthropic) │
        └─────────────────────┘   └──────────────────────┘
```

## Running the REST API server

```bash
# Development
uvicorn modular_rag.api:create_app --factory \
        --reload \
        --host 0.0.0.0 \
        --port 8000

# Pass manifest path via environment variable
MRAG_MANIFEST_PATH=manifests/presets/secure-enterprise-rag.yaml \
uvicorn modular_rag.api:create_app --factory --host 0.0.0.0 --port 8000
```

## Docker

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install -e ".[v1]"

ENV MRAG_MANIFEST_PATH=manifests/presets/secure-enterprise-rag.yaml

EXPOSE 8000
CMD ["uvicorn", "modular_rag.api:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml

```yaml
version: "3.9"

services:
  mrag-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MRAG_OPENAI_API_KEY=${OPENAI_API_KEY}
      - MRAG_QDRANT_URL=http://qdrant:6333
      - MRAG_MANIFEST_PATH=manifests/presets/secure-enterprise-rag.yaml
    depends_on:
      - qdrant

  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  qdrant_data:
```

```bash
docker-compose up -d
```

## Multi-environment manifests

Use the environment-specific manifests under `manifests/`:

```
manifests/
├── dev/         # local dev, logging verbose, no auth
├── staging/     # mirrors production, auth enabled, GPT-4o
└── production/  # full security stack, multi-tenant, audit trail
```

Select the environment at runtime:

```bash
export MRAG_ENVIRONMENT=production
export MRAG_MANIFEST_PATH=manifests/production/pipeline.yaml
```

## Health check

```bash
curl http://localhost:8000/health
# {"status": "ok", "pipeline": "secure-enterprise-rag", "version": "0.x.y"}
```

## Scaling

- **Horizontal**: The `RAGEngine` is stateless — scale the API containers freely. The BM25 index must be rebuilt per-container on startup (or replaced with a shared search service in V4).
- **Qdrant**: Use the Qdrant cluster mode for production workloads. Configure the URL and API key via `MRAG_QDRANT_URL` and `MRAG_QDRANT_API_KEY`.
- **Embedding**: Consider a dedicated embedding service (e.g., Infinity, TEI) to avoid reloading the model on each container restart. Wire it via the `adapters/embeddings/` adapter.

## Security hardening for production

1. Enable `BasicSecurityGuard` and `PatternRedactor` in your manifest.
2. Set `MRAG_QDRANT_API_KEY` — Qdrant supports API-key authentication.
3. Put the API behind an authenticated reverse proxy (nginx, Traefik, or your API gateway).
4. Use the `secure-enterprise-rag.yaml` preset as your base, or create a `manifests/production/` override.
5. Set `MRAG_LOG_LEVEL=WARNING` in production to suppress debug trace output.
