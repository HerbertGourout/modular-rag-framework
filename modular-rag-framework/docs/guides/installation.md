# Installation

## Requirements

- Python 3.11 or later
- Git
- Access to at least one LLM backend (OpenAI, Azure OpenAI, or Anthropic)
- Optional: Docker (for Qdrant vector store)

## Development installation

Clone the repository and install in editable mode:

```bash
git clone https://pscode.lioncloud.net/data_specialiste/advancedpublicisrag.git
cd advancedpublicisrag/modular-rag-framework
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -e ".[v1,dev]"
```

## Extras

The project uses optional dependency groups. Install only what you need:

| Group | Install command | What it adds |
|---|---|---|
| `v1` | `pip install -e ".[v1]"` | Core RAG: Qdrant, rank-bm25, sentence-transformers, openai, anthropic, pymupdf |
| `v3` | `pip install -e ".[v3]"` | Graph memory: networkx, spacy |
| `v4` | `pip install -e ".[v4]"` | Governance: OPA bindings, policy validators |
| `v5` | `pip install -e ".[v5]"` | Multimodal: PIL, whisper, timm |
| `dev` | `pip install -e ".[dev]"` | Testing and linting: pytest, mypy, ruff, pytest-asyncio |
| `all` | `pip install -e ".[all]"` | Everything |

## Running Qdrant locally (V1)

Qdrant is the default vector store for V1. Start it with Docker:

```bash
docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

Or add it to a `docker-compose.yml`:

```yaml
services:
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - ./qdrant_data:/qdrant/storage
```

The default manifest (`manifests/presets/local-hybrid-rag.yaml`) connects to `localhost:6333`.

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `MRAG_OPENAI_API_KEY` | OpenAI API key | — |
| `MRAG_ANTHROPIC_API_KEY` | Anthropic API key | — |
| `MRAG_QDRANT_URL` | Qdrant server URL | `http://localhost:6333` |
| `MRAG_QDRANT_COLLECTION` | Qdrant collection name | `mrag_default` |
| `MRAG_EMBEDDING_MODEL` | HuggingFace embedding model name | `BAAI/bge-small-en-v1.5` |
| `MRAG_ENVIRONMENT` | Runtime environment (`dev`/`staging`/`production`) | `dev` |
| `MRAG_LOG_LEVEL` | Structlog level | `INFO` |

Create a `.env` file at the project root and export these variables, or set them in your shell before running the CLI or API server.

## Verifying the installation

```bash
mrag version
```

Expected output: `Modular RAG Framework vX.Y.Z`.

> At the current pre-alpha stage (`v0.0.x`), this command confirms the package is importable. Full end-to-end verification will be available at `v0.1` with `examples/simple_qa/`.
