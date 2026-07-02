---
description: Run the fast unit test suite for Modular RAG without external services.
argument-hint: "[pytest args]"
disable-model-invocation: true
---

# Unit Test Workflow

Run the unit test suite only. Append any user-provided arguments after the test path:

```powershell
pytest tests/unit $ARGUMENTS
```

If a local virtual environment exists, prefer:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit $ARGUMENTS
```

Do not run integration or e2e tests from this skill. Summarize failures by test name, file, and likely cause.
