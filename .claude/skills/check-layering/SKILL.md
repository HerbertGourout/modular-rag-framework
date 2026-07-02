---
description: Audit Modular RAG hexagonal layering and domain import boundaries.
disable-model-invocation: true
---

# Layering Audit

Run the import boundary checker:

```powershell
python scripts/check_layering.py
```

The default mode ignores entries listed in `.claude/layering-baseline.txt` and fails
only on new violations. To inspect all current debt, run:

```powershell
python scripts/check_layering.py --strict --show-baseline
```

If a local virtual environment exists, prefer:

```powershell
.\.venv\Scripts\python.exe scripts/check_layering.py
```

Treat findings as architecture issues, not style issues. For each violation, explain:

1. The importing file.
2. The imported module.
3. The violated boundary.
4. The smallest likely refactor, usually through `contracts/`, `core/models/`, or orchestration wiring.
