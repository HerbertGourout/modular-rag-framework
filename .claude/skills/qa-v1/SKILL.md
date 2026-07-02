---
description: Run the recommended V1 local quality gate after code changes.
argument-hint: "[extra pytest args]"
disable-model-invocation: true
---

# V1 Quality Gate

Run the local checks that do not require Qdrant or LLM API keys:

```powershell
ruff check src/modular_rag tests
pytest tests/unit tests/contract $ARGUMENTS
python scripts/check_layering.py
```

If a local virtual environment exists, prefer:

```powershell
.\.venv\Scripts\ruff.exe check src/modular_rag tests
.\.venv\Scripts\python.exe -m pytest tests/unit tests/contract $ARGUMENTS
.\.venv\Scripts\python.exe scripts/check_layering.py
```

Do not run `tests/integration` unless Qdrant is confirmed on `localhost:6333`.
Do not run `tests/e2e` unless Qdrant and the required LLM API key are confirmed.

Report results in this order: lint, unit tests, contract tests, layering. Include the exact failing command for any failure.
