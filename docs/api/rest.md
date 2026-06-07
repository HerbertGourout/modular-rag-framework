# REST API Reference

The Modular RAG Framework ships a FastAPI application (`src/modular_rag/api/`).
Start it with:

```bash
uvicorn modular_rag.api:create_app --factory --host 0.0.0.0 --port 8000
```

Base URL: `http://localhost:8000`

---

## Endpoints

### `GET /health`

Health check. Returns HTTP 200 when the pipeline is loaded and ready.

**Response**

```json
{
  "status": "ok",
  "pipeline": "local-hybrid-rag",
  "version": "0.0.1"
}
```

---

### `POST /answer`

Submit a question and receive a grounded answer with citations.

**Request body**

```json
{
  "question": "What are the main conclusions of the Q3 report?",
  "k": 5
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | `string` | Yes | The user question |
| `k` | `integer` | No | Number of chunks to retrieve (default: 5) |

**Response**

```json
{
  "answer": "The main conclusions of the Q3 report are...",
  "citations": [
    {
      "source": "Q3-report.pdf",
      "passage": "Revenue grew 12% year-over-year...",
      "score": 0.92,
      "page": 4
    },
    {
      "source": "Q3-summary.md",
      "passage": "Key highlights include a 15% reduction...",
      "score": 0.87,
      "page": null
    }
  ],
  "trace_id": "a1b2c3d4",
  "model": "gpt-4o-mini"
}
```

**Error responses**

| Status | When |
|---|---|
| `403 Forbidden` | Security guard blocked the query (injection detected, query too long, policy violation) |
| `422 Unprocessable Entity` | Invalid request body (e.g., missing `question`) |
| `500 Internal Server Error` | LLM API failure, Qdrant unreachable, or unexpected exception |

---

### `GET /retrieve`

Retrieve chunks for a query without generating an answer. Useful for debugging retrieval quality.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | `string` | Required | The search query |
| `k` | `integer` | `10` | Number of chunks to return |

**Request**

```
GET /retrieve?q=BM25+retrieval+model&k=5
```

**Response**

```json
[
  {
    "chunk_id": "uuid-...",
    "doc_id": "uuid-...",
    "content": "BM25 is a probabilistic retrieval model based on term frequency...",
    "source": "retrieval-methods.md",
    "score": 0.87,
    "rank": 1,
    "retrieval_method": "hybrid"
  }
]
```

---

## Authentication

At the current pre-alpha stage, there is no built-in authentication.
In production:

1. Put the API behind an authenticated reverse proxy or API gateway.
2. V4 will add per-tenant API keys and JWT validation via `adapters/auth/`.

---

## OpenAPI docs

When the server is running, interactive docs are available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## Client example (Python)

```python
import httpx

client = httpx.Client(base_url="http://localhost:8000")

response = client.post("/answer", json={
    "question": "Explain the hybrid retrieval approach.",
    "k": 5,
})
response.raise_for_status()
data = response.json()

print(data["answer"])
for cit in data["citations"]:
    print(f"  [{cit['source']}] {cit['passage'][:80]}")
```

## Client example (curl)

```bash
curl -s -X POST http://localhost:8000/answer \
     -H "Content-Type: application/json" \
     -d '{"question": "What is GraphRAG?", "k": 5}' \
     | python -m json.tool
```
