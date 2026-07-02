---
description: Run Protocol conformance tests for Modular RAG contracts.
argument-hint: "[pytest args]"
disable-model-invocation: true
---

# Contract Test Workflow

Run the contract conformance suite only. Append any user-provided arguments after the test path:

```powershell
pytest tests/contract $ARGUMENTS
```

If a local virtual environment exists, prefer:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contract $ARGUMENTS
```

Use this after changing `src/modular_rag/contracts/` or adding a new Protocol implementation. If a new implementation is missing from a conformance test, report that as the primary fix.
