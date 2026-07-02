---
description: Run the simple QA example pipeline for a local V1 smoke test.
argument-hint: "[question]"
disable-model-invocation: true
---

# Simple QA Smoke Test

Use this workflow to validate the V1 example. It may require Qdrant and an LLM API key.

1. Confirm Qdrant is running on `localhost:6333`.
2. Confirm at least one required LLM environment variable is set.
3. Ingest the bundled example docs:

```powershell
python examples/simple_qa/main.py ingest examples/simple_qa/docs/
```

4. Ask the provided question, or use `What is RAG?` if no question was provided:

```powershell
python examples/simple_qa/main.py ask "$ARGUMENTS"
```

If `$ARGUMENTS` is empty, run:

```powershell
python examples/simple_qa/main.py ask "What is RAG?"
```

Summarize whether ingest succeeded, whether retrieval/generation succeeded, and which dependency failed if the smoke test cannot run.
