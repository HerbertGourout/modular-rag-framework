# CLAUDE.local.md Example

Copy this file to `CLAUDE.local.md` for personal project preferences. Do not commit
`CLAUDE.local.md`.

## Local Services

- Qdrant URL: `http://localhost:6333`
- Preferred manifest: `manifests/presets/local-hybrid-rag.yaml`

## Environment

Set only the keys you need in your shell, `.env`, or local profile:

```powershell
$env:MRAG_OPENAI_API_KEY = "sk-..."
$env:MRAG_ANTHROPIC_API_KEY = "sk-ant-..."
```

## Personal Workflow Notes

- Prefer `.venv\Scripts\python.exe -m pytest` when the virtual environment exists.
- Run `/qa-v1` before opening a GitHub PR.
- Run `/run-simple-qa` only when Qdrant and an LLM API key are available.
