# CLAUDE.local.md Example

Copy this file to `CLAUDE.local.md` for personal project preferences. Do not commit
`CLAUDE.local.md`.

## Local Services

- Qdrant URL: `http://localhost:6333`
- Preferred manifest: `manifests/presets/local-hybrid-rag.yaml`

## Environment

Set only the keys you need in your shell, `.env`, or local profile — use the SDKs' own standard
names, not `MRAG_`-prefixed ones (`app/settings.py`'s `Settings` class declares those but they're
never read anywhere in the real pipeline-wiring path):

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

## Personal Workflow Notes

- Prefer `.venv\Scripts\python.exe -m pytest` when the virtual environment exists.
- Run `/qa-v1` before opening a GitHub PR.
- Run `/run-simple-qa` only when Qdrant and an LLM API key are available.
