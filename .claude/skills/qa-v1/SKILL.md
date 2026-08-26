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

Do not run the complete `tests/integration` directory unless Qdrant and PostgreSQL are confirmed.
Do not run the complete `tests/e2e` directory unless Qdrant, PostgreSQL and the required LLM API
key are confirmed; individual deterministic scenarios have narrower prerequisites.

Report results in this order: lint, unit tests, contract tests, layering. Include the exact failing command for any failure.
