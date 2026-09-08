"""Provider-egress control (Lot 20, docs/refactoring-plan.md — "Data
Classification and LLM Egress Control"). Closes the gap named throughout
docs/architecture/threat-model.md and data-classification-policy.md: output
redaction runs after generation, so it cannot stop raw query text, retrieved
context, document content, or embedding input from reaching a remote
provider before that point. This module defines the fail-closed decision
point that goes before it.

Deliberately vendor-neutral, per CLAUDE.md §07/`.claude/rules/contracts.md`:
no provider name (OpenAI, Anthropic, ...) appears here. `provider` is a
manifest-supplied identifier (the wired component's `ComponentConfig.type`
string, e.g. "sentence-transformers"/"openai"/"anthropic" — not the
component's own `.name()`, which several adapters make dynamic/model-specific
and therefore unstable as a policy-config key); what each provider is
permitted to receive is entirely manifest configuration, read by whichever
`EgressPolicy` implementation is wired.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from modular_rag.core.enums import DataClassification


class EgressOperation(StrEnum):
    """Which owned external-provider boundary an egress decision covers.

    RERANK is included even though the only registered reranker today
    (`retrieval.rerankers.cross_encoder.CrossEncoderReranker`) executes
    locally via `sentence-transformers` — so a check for it always resolves
    to a "local" allow under any `EgressPolicy` implementation that honors
    the `local` provider-profile flag — because a future remote reranker
    adapter must not require inventing a new operation type to be covered.
    """

    EMBED = "embed"
    GENERATE = "generate"
    RERANK = "rerank"


@dataclass(frozen=True)
class EgressDecision:
    """Content-free result of one egress check — every field here is safe to
    log or place in an `AuditEvent` payload verbatim; none of them is or
    contains the classified query/chunk/document text itself."""

    allowed: bool
    reason: str
    classification: DataClassification | None
    provider: str
    operation: EgressOperation


@runtime_checkable
class EgressPolicy(Protocol):
    """Fail-closed, classification-aware gate evaluated immediately before an
    owned component would send content to an external provider.

    `security.policies.egress_policy.ManifestEgressPolicy` is the reference
    implementation, registered on `Container.egress_policy` — optional,
    mirrors `TenantPolicy`'s optionality (`contracts.security.TenantPolicy`):
    a pipeline with no `governance.egress_policy` configured behaves exactly
    as it did before this lot existed. An operator handling any
    classified/sensitive content through a remote provider must configure
    one explicitly — this is not automatic, the same way `tenant_policy` and
    `redactor` are not automatic.
    """

    def check(
        self,
        *,
        classification: DataClassification | None,
        provider: str,
        operation: EgressOperation,
    ) -> EgressDecision: ...

    def name(self) -> str: ...
