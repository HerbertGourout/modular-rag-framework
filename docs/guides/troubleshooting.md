# Troubleshooting

This guide covers the errors and dead ends a new contributor is most likely to hit in the
first few days — from a missing service to a cross-domain import the layering audit rejects.
Each entry follows the same shape: what you'll see, why it happens, how to fix it. If your
error isn't listed here, check [CLAUDE.md](../../CLAUDE.md) section 09 for known stubs, or
[ROADMAP.md](../../ROADMAP.md) to confirm the feature you're hitting is actually supposed to
work yet.

---

## Setup and environment

### `ModuleNotFoundError: No module named 'pytest'` (or `qdrant_client`, `sentence_transformers`, etc.)

**Why**: the dev/V1 dependency groups aren't installed, or you're running the wrong Python
interpreter (a global install instead of the project's `.venv`).

**Fix**:
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[v1,dev]"
```
If a `.venv` already exists, make sure it's actually activated — `pip install -e ".[v1,dev]"`
into the wrong interpreter is the single most common cause of "it worked yesterday."

### `mrag: command not found` after installing

**Why**: the CLI entry point (`mrag` → `modular_rag.cli:app`) is installed into the active
virtualenv's `Scripts/`/`bin/` folder. If you installed in one shell and are running `mrag`
in another (or in a shell where the venv isn't activated), the command won't resolve.

**Fix**: activate the same `.venv` you installed into, or call it explicitly:
`.venv\Scripts\mrag.exe ask ...` (Windows) or `.venv/bin/mrag ask ...` (Linux/macOS).

### `mrag version` runs, but `mrag ask` fails immediately

**Why**: `mrag version` only proves the package imports — it doesn't touch Qdrant, the
manifest, or an LLM API key. `mrag ask` exercises the full pipeline. See the next two
sections before assuming something is broken in the code itself.

---

## Connecting to services

### `ConnectionRefusedError` / `httpx.ConnectError` pointing at `localhost:6333`

**Why**: Qdrant isn't running, or the manifest's `indexer.config.url` points somewhere else
than where it is listening.

**Fix**:
```bash
docker run -d -p 6333:6333 qdrant/qdrant
curl http://localhost:6333/healthz   # should return "healthz check passed"
```
See [installation.md](installation.md), "Running Qdrant locally."

### `AuthenticationError` / `401` from OpenAI or Anthropic

**Why**: the standard SDK env vars (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`) are missing,
expired, or set in a shell/session different from the one running `mrag`/`uvicorn` — **not**
`MRAG_OPENAI_API_KEY`/`MRAG_ANTHROPIC_API_KEY`. `app/settings.py`'s `Settings` class once
declared those `MRAG_*` names, but nothing in the real pipeline-wiring path ever constructed
`Settings`/called `get_settings()` — the generators fall through to the OpenAI/Anthropic SDK's
own default env-var lookup whenever the manifest doesn't set `api_key` explicitly. That file was
orphaned and was deleted outright in Étape 8 of the ADR-0007 stabilization pass.

**Fix**: confirm `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` is set in the exact shell you're running
from (`echo $env:OPENAI_API_KEY` in PowerShell), then restart the process — restarting matters
because the SDK client reads the env var once at construction time, not per request.

### Everything ingests fine, but `mrag ask` returns no relevant chunks / empty citations

**Why, in order of likelihood**:
1. You ingested into a different Qdrant collection than the one the manifest queries (check
   the manifest's `collection` value matches on both sides).
2. If the manifest's `retriever.config.lexical` is left unset or `"bm25-memory"` (the local
   preset's default), the lexical half of hybrid retrieval is in-memory and rebuilt per process —
   if you ingested in one process and are querying in a freshly started one, the BM25 index is
   empty even though Qdrant still has the vectors from before. (See
   [installation.md](installation.md) and [data-model.md](../architecture/data-model.md) on why
   BM25 has no persistence there.) A manifest with `lexical: sparse-qdrant` instead (see
   `manifests/presets/secure-enterprise-rag.yaml`) does not have this gap — its lexical index is
   a persistent Qdrant collection, same durability as the vector side.
3. The question genuinely doesn't match anything in the corpus — try `GET /retrieve` or
   `mrag ask` with a very literal question drawn straight from a sentence you know is in
   the ingested documents, to rule out a real retrieval-quality problem.

---

## Configuration and manifests

### `RegistryError: no factory registered for ('chunker', 'my-thing')`

**Why**: the manifest's `type:` field doesn't match any name registered in
`app/default_factories.py`. This is by design — see
[CLAUDE.md](../../CLAUDE.md) rule 03: nothing runs unless it's registered *and* selected by
name in YAML.

**Fix**: check the exact string in `app/default_factories.py`'s `reg.register("chunker", "...",
...)` call and make sure the manifest's `type:` matches it character for character (typos
and hyphen/underscore mismatches are the usual culprit). If you're adding a new component,
see [plugin-development.md](plugin-development.md).

### `ManifestError` / Pydantic `ValidationError` when loading a YAML manifest

**Why**: the YAML doesn't match `PipelineManifest`'s schema — a required section is missing,
a field has the wrong type, or the indentation is off (a common YAML trap: mixing tabs and
spaces, or a list item that isn't indented under its parent key).

**Fix**: start from a working preset (`manifests/presets/local-hybrid-rag.yaml`) and change
one section at a time rather than writing a manifest from scratch — it's much faster to spot
which single edit broke validation.

### `SecurityError`: query blocked before it even reaches retrieval

**Why**: `BasicSecurityGuard.check_query()` matched an injection pattern, a blocked term, or
the query exceeded `max_query_length`. This is often a **false positive** during local
testing — e.g., a question that happens to contain "ignore" near "instructions", or a test
string with `exec(` in it.

**Fix**: see the exact patterns in [security.md](../architecture/security.md) to understand
why a specific query was blocked. In a dev manifest, you can disable the guard entirely
(`security: {guard: null}`) — never do this in a manifest meant to represent a production or
client-facing configuration.

---

## Architecture and layering

### `scripts/check_layering.py` reports a new violation

**Why**: a domain module (`retrieval/`, `generation/`, `security/`, etc.) imported from
another domain module, or `contracts/`/`core/` imported something they shouldn't have. See
[module-model.md](../architecture/module-model.md) for the worked examples of exactly this
failure mode.

**Fix**: move the shared type into `core/models/` if it's data, add or extend a Protocol in
`contracts/` if it's behavior, or wire the two components together through
`orchestration/registry.py` instead of a direct import. Do not add the violation to
`.claude/layering-baseline.txt` to silence it — that file exists to track *pre-existing* debt,
not to launder new debt.

### A contract test fails with `isinstance(obj, SomeProtocol)` returning `False`

**Why**: your new implementation is missing a method the Protocol requires, or a method
signature doesn't match closely enough for `@runtime_checkable` structural typing to
recognize it (note: `runtime_checkable` only checks method *names* exist, not their
signatures — a `False` result usually means a method is missing entirely, not just typed
differently).

**Fix**: compare your class's method list against the Protocol definition in `contracts/`
line by line. See [plugin-development.md](plugin-development.md) for the full four-step
recipe.

### I get `NotImplementedError` from a component I expected to work

**Why**: you're likely calling into a stub reserved for a later version, or a method a real
adapter deliberately doesn't implement yet. Two of the four historically-`.gitkeep`-only
`adapters/` subdirectories now hold real code — `adapters/llms/langgraph_engine.py`
(`LangGraphEngineAdapter`) and `adapters/auth/keycloak_verifier.py` (`KeycloakTokenVerifier`) —
so a `NotImplementedError` from either of those means a specific unimplemented method on a real
class (check that class directly), not a missing file. `adapters/graphstores/` and
`adapters/search/` are still genuinely `.gitkeep`-only placeholders (see
[CLAUDE.md](../../CLAUDE.md) section 09 and [structure.md](../architecture/structure.md)). One
other real, expected `NotImplementedError`: `QdrantStore.retrieve()` (the bare, embedder-less
`Retriever`-shaped call) always raises it by design — use `VectorRetriever`, or call
`retrieve_by_vector()` directly with a vector you already computed. Check
[ROADMAP.md](../../ROADMAP.md) and [capability-matrix.md](../architecture/capability-matrix.md)
to confirm the capability you're expecting has actually shipped before assuming it's a bug.

---

## Git and Windows-specific issues

### `git checkout` / `git merge` fails with `invalid path '...:Zone.Identifier'`

**Why**: a file with a literal colon in its name was committed (typically a Windows
"downloaded from the internet" marker, `filename.pdf:Zone.Identifier`, accidentally staged
by `git add -A` on a Windows machine). NTFS interprets the colon as an alternate-data-stream
separator, and Git for Windows blocks the checkout by default (`core.protectNTFS`) as a
security measure against a known class of exploit.

**Fix**: if you trust the source of the branch/commit, temporarily run
`git config core.protectNTFS false`, complete the checkout/merge, then remove the offending
files from tracking and reset the config:
```bash
git config core.protectNTFS false
git merge <branch>
git rm --cached "path/to/file:Zone.Identifier"
git config --unset core.protectNTFS
```
Add `*:Zone.Identifier` to `.gitignore` to prevent recurrence. Never leave
`core.protectNTFS` disabled longer than the one operation that needed it.

### The post-edit Ruff hook doesn't seem to run, or silently does nothing

**Why**: `.claude/hooks/post-edit-quality.ps1` looks for `.venv\Scripts\ruff.exe` first, then
falls back to `ruff` on `PATH`. If neither exists, it prints a message and exits `0`
(non-fatal by design) — easy to miss in a busy terminal.

**Fix**: `pip install -e ".[dev]"` inside the project's `.venv` so `ruff` is present at the
path the hook checks first.

---

## When none of this matches

Check, in order: [CLAUDE.md](../../CLAUDE.md) section 09 (known stubs), the relevant
[ADR](../adr/_index.md) for *why* something is built the way it is, and
[docs/archive/2026-05-20-initial-review.md](../archive/2026-05-20-initial-review.md) for
historical context on decisions that might explain an unexpected constraint. If it's a new
failure mode nobody has hit yet, add it here once you've solved it — this file is only as
useful as it is current.
