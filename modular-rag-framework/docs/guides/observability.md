# Observability Guide

## What the framework tracks

Every call to `pipeline.answer()` produces a `Trace` object (see `core/models/trace.py`).
The trace records each pipeline step with:

- **Name** — e.g., `guard_query`, `retrieve`, `rerank`, `generate`, `guard_answer`
- **Input / output tokens** — for LLM steps
- **Latency (ms)** — wall-clock time for the step
- **Metadata** — arbitrary key/value pairs (e.g., `num_chunks_retrieved: 20`)

The `Trace` accumulates totals: `total_input_tokens`, `total_output_tokens`, `total_latency_ms`.

## Telemetry backends

The telemetry contract (`contracts/telemetry.py`) defines two methods:

```python
record_trace(trace: Trace) -> None
record_metrics(pipeline_id: str, metrics: Metrics) -> None
```

### StructlogTelemetry (default)

Configured automatically when no custom telemetry is specified in the manifest.
Writes structured JSON to stdout:

```json
{
  "event": "trace_recorded",
  "pipeline_id": "local-hybrid-rag",
  "query_id": "a1b2c3d4",
  "total_latency_ms": 1234.5,
  "total_input_tokens": 1800,
  "total_output_tokens": 320,
  "routing_strategy": "simple_rag",
  "steps": ["guard_query", "retrieve", "rerank", "generate", "guard_answer"],
  "timestamp": "2026-05-21T10:00:00Z"
}
```

### NullTelemetry

Use in tests to suppress all telemetry output:

```python
from modular_rag.observability import NullTelemetry

container.telemetry = NullTelemetry()
```

### Custom telemetry adapter

Implement the `Telemetry` protocol and wire it in your manifest:

```python
# src/my_org/telemetry/datadog_telemetry.py
from modular_rag.contracts.telemetry import Telemetry
from modular_rag.core.models.trace import Trace
from modular_rag.core.models.metrics import Metrics

class DatadogTelemetry:
    def record_trace(self, trace: Trace) -> None:
        # send to Datadog APM
        ...

    def record_metrics(self, pipeline_id: str, metrics: Metrics) -> None:
        # send custom metric
        ...

    def name(self) -> str:
        return "datadog"
```

Register and use in your manifest:

```yaml
telemetry:
  type: datadog
  config:
    api_key: ${DATADOG_API_KEY}
    service: mrag-pipeline
```

## Reading traces in Python

```python
pipeline = load_pipeline("manifests/presets/local-hybrid-rag.yaml")
answer = pipeline.answer("What is GraphRAG?")

# The trace_id links the answer to its trace
print(answer.trace_id)
```

## Evaluation metrics

After running a benchmark, metrics are emitted via `record_metrics()`:

| Metric | Description |
|---|---|
| `recall_at_k` | Fraction of relevant documents in top-k retrieved |
| `precision_at_k` | Fraction of top-k that are relevant |
| `ndcg` | Normalized Discounted Cumulative Gain |
| `mrr` | Mean Reciprocal Rank |
| `groundedness` | Overlap between answer and retrieved context |
| `faithfulness` | Whether the answer contradicts the context |
| `answer_relevance` | Whether the answer addresses the query |
| `latency_ms` | End-to-end wall-clock time |
| `input_tokens` | Total LLM input tokens |
| `output_tokens` | Total LLM output tokens |
| `cost_usd` | Estimated API cost |

## Log configuration

Set the log level via environment variable:

```bash
export MRAG_LOG_LEVEL=DEBUG   # verbose tracing
export MRAG_LOG_LEVEL=INFO    # default
export MRAG_LOG_LEVEL=WARNING # production (suppress trace-level output)
```

Structlog outputs JSON by default. To switch to a human-readable format for development, set:

```bash
export MRAG_LOG_FORMAT=console
```
