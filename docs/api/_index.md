# API — Overview

The framework exposes two user-facing surfaces on top of the same engine (`RAGEngine`): a
CLI (`mrag`, described in [CLAUDE.md](../../CLAUDE.md)) for scriptable command-line use, and
a FastAPI REST API for integration into a third-party application (frontend, client backend
service, chatbot). Both call exactly the same orchestration code — there is no duplicated
logic between the two surfaces, only a difference in input/output format.

**Why a REST API rather than just a Python library?** Many clients already have an
application (internal portal, Teams/Slack chatbot, existing backend) and want to call the
RAG pipeline as a service, without embedding heavy Python dependencies
(sentence-transformers, qdrant-client) into their own application stack.

- [rest.md](rest.md) — complete reference for the endpoints (`/health`, `/answer`,
  `/retrieve`), request/response schemas, error codes, Python and `curl` examples.

At this stage (pre-V4), the API has no built-in authentication — see the "Authentication"
section of [rest.md](rest.md) for the recommended posture while waiting for `adapters/auth/`.
