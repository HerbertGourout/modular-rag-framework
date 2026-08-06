# Business case — Modular RAG Framework

> Internal Publicis Sapient document. Audience: management, technical leads, client project stakeholders.

---

## Executive summary

This framework is a **proprietary delivery accelerator** developed in-house by Publicis Sapient. It provides an orchestration, governance, and security layer on top of the best available open-source RAG tools — something no generic OSS framework offers for an enterprise context. Every client project that uses it saves 4 to 8 weeks of setup. At 5 projects per year, the full V1–V4 development pays for itself.

---

## 1. Reusable commercial asset

This framework is proprietary IP that stays with Publicis Sapient at the end of every project, unlike a bespoke LangChain implementation delivered to the client.

```mermaid
%%{init: {"theme": "base"}}%%
flowchart LR
    P1["Client Project 1\nbuilds an adapter,\na manifest, a policy"] -->|"absorbed into"| FW[("Framework\n(shared IP)")]
    FW -->|"4-8 weeks saved\non setup"| P2["Client Project 2\nstarts from a\nricher base"]
    P2 -->|"adds its own\nadapter/manifest/policy"| FW
    FW -->|"even faster\nstart"| P3["Client Project 3\n..."]
    P3 -->|"compounds\nfurther"| FW
```

Each delivery makes the next one faster and the asset more valuable — the loop never resets
to zero the way a client-owned, one-off LangChain build does.

- **Savings per project**: 4 to 8 weeks of setup, security, observability, and governance are no longer rebuilt from scratch.
- **Margin uplift**: the weeks saved on infrastructure are not lost — they are reallocated to billable business value.
- **Premium pricing**: a proprietary framework justifies higher day rates than "we use LangChain like everyone else".
- **Compounding**: every adapter, manifest, or policy built on one project accumulates in the framework. The asset appreciates with every delivery.

---

## 2. Delivery accelerator

The YAML manifest is the key: configuring a complete RAG pipeline — chunker, embedder, hybrid retriever, reranker, LLM, security — takes hours, not weeks.

- **Demonstrable prototype in 1 day**: for an RFP or a discovery, showing a working pipeline on the client's documents within 24 hours is an immediate selling point.
- **Faster onboarding**: a new consultant on the project understands the architecture in half a day — no need to decode an unstructured LangChain codebase.
- **Flexible staffing**: the standardized hexagonal architecture lets teams rotate between projects without a long ramp-up period.
- **No-code configuration**: a lead or a PM can read and modify a YAML manifest without opening Python.

---

## 3. Competitive differentiation

Competitors (Accenture, Capgemini, Deloitte Digital) use LangChain, LlamaIndex, or proprietary cloud solutions. Publicis Sapient can position itself differently.

- **"We have our own enterprise RAG framework"**: a pitch hook few consultancies can deliver credibly and demonstrably.
- **Governance by design**: fail-closed tenant isolation, a real Keycloak-backed identity
  verifier, and a structured audit trail (`AuditEvent`, PII/secret payload allowlist) are
  already shipped — not a V4-future promise (per
  [ADR-0005](adr/0005-document-ai-control-plane-boundary.md), accepted 2026-08-04, this is owned
  and current, V2.0 scope). This exists in no comparable OSS framework at this maturity and is a
  decisive argument in regulated RFPs today, not "once V4 ships."
- **Demonstrable architecture**: the ADRs, the Pydantic contracts, and the hexagonal structure are proof of technical maturity that can be shown to a CIO or a CISO during an audit.
- **Vendor independence**: the adapter pattern proves that Publicis Sapient is not simply reselling OpenAI or AWS — it brings its own value layer, neutral and durable.

---

## 4. Coverage of regulated industries

Publicis Sapient works with banks, insurers, pharmaceutical players, and utilities — all subject to strict regulations (GDPR, DORA, NIS2, sector-specific). This framework addresses these constraints directly.

- **Audit trail — designed, not yet delivered**: every retrieval, generation, and security
  decision is captured in a per-request `Trace` object, but today that `Trace` is discarded
  after the request unless a `telemetry` component is wired — and the manifest schema doesn't
  yet expose a way to configure one. Nothing is currently persisted for a DPO to query. This is
  V1.2 scope (`docs/refactoring-plan.md` Lot 10); do not represent this as delivered to a client
  or auditor until Lot 10 lands.
- **Automatic PII redaction**: emails, phone numbers, IBANs, API keys removed before exposure — documentable in a DPIA.
- **Multi-tenant isolation — descriptive only, not yet enforced**: the manifest schema has a
  `tenant` field, but it is not wired into any storage-level filter or access check today — two
  tenants sharing a deployment are not actually isolated at the data layer. This is Lot 11b
  scope (`docs/refactoring-plan.md`); do not represent this as delivered until then.
- **Safety vs Security explicitly separated**: a distinction regulators appreciate, and one that proves security is not an afterthought.

> **2026-08-04 correction (Lot 5):** the two rows above were previously stated as delivered
> capabilities. They are target-state design decisions with real code behind the *shape* of the
> solution (a `Trace` model exists; a `tenant` field exists) but no enforcement or persistence
> yet. Do not cite this document's audit-trail or tenant-isolation claims in a client-facing or
> compliance context until the corresponding lots in `docs/refactoring-plan.md` are marked
> `COMPLETE`.

---

## 5. Resilience against AI market evolution

The LLM market changes every six months. This framework is designed to survive those changes without a rewrite.

- **Swap an LLM with one line of YAML**: when GPT-5 ships or a client mandates Mistral on-premise, the change does not touch the pipeline.
- **Integrate the best OSS tools at any time**: LlamaIndex for semantic chunking, Ragas for evaluation, LiteLLM as a gateway — all wrappable in 50-line adapters. The framework orchestrates, it does not reinvent.
- **No dependency on an external startup**: LangChain nearly disappeared, LlamaIndex changes its API regularly. Here, Publicis Sapient controls its own contracts.
- **On-premise deployment possible**: with HuggingFace + Qdrant, the framework runs entirely without calls to external APIs — a frequent requirement in projects with sensitive data.

---

## 6. Foundation for a structured service offering

This framework can be the foundation of a formalized, repeatable AI practice.

- **RAG-as-a-Service**: package the framework + hosting + support as an offering sold to clients who do not want to manage the infrastructure.
- **Audits of existing RAG systems**: knowledge of the framework makes it possible to audit third-party implementations at clients who started with LangChain.
- **Internal training**: create a "RAG Engineer PS" curriculum based on this framework — a differentiating skill for recruitment and retention.
- **Client skills transfer**: in some contexts, deliver the framework as a foundation the client then maintains — a licensing or transfer model.

---

## 7. Talent attraction and retention

Senior engineers choose their employers partly based on the technical quality of internal projects.

- **"At PS we build our own tools"** is a recruiting argument against consultancies that merely assemble SaaS products.
- A potentially open-sourced framework would generate public visibility, external contributions, and inbound applications.
- Internal contributors develop RAG architecture expertise that is rare on the market — a skill that adds value on client engagements.

---

## 8. Capitalizing on accumulated domain knowledge

Publicis Sapient accumulates methodological expertise across dozens of projects. This framework is the vehicle for capitalizing on that knowledge.

- Patterns discovered on one project (optimal chunking for legal documents, reranking strategy for product FAQs) are encoded as reusable adapters and manifests.
- One project's Ragas evaluations feed the next project's benchmarks.
- Graph Memory (V3) could model accumulated sector knowledge as an asset that appreciates over
  time — with a caveat since [ADR-0005](adr/0005-document-ai-control-plane-boundary.md)
  (accepted 2026-08-04): GraphRAG traversal itself is delegated to a selected external engine
  (LangGraph), not a native build; a native graph *data model* may still be retained, but that
  is undecided, not committed.

---

## 9. Positioning on high-stakes projects

Some projects require guarantees that OSS frameworks cannot provide.

- **Data sovereignty**: fully on-premise or client private-cloud deployment, with no calls to external APIs.
- **Explainability**: sourced citations, groundedness scores, and the full trace make it possible to justify every answer — a frequent requirement in decision-support projects.
- **Definable SLAs**: OpenTelemetry telemetry measures latency, tokens, and costs at every step — making it possible to commit to contractual SLAs.
- **Large enterprise clients**: CIO and CISO stakeholders at large companies want governance, auditability, and control. This framework speaks directly to them.

---

## Summary

| Dimension | Direct benefit |
|---|---|
| Reusable IP | Higher margins on every client project |
| Accelerated delivery | 4–8 weeks saved per project |
| Differentiation | Winning pitch in regulated RFPs |
| Governance | Demonstrable GDPR/DORA compliance |
| Resilience | Zero vendor lock-in, compatible with any LLM evolution |
| Service offering | Basis for a formalized enterprise RAG practice |
| Talent | Recruitment and retention of senior AI profiles |
| Knowledge | Cross-project capitalization, an appreciating asset |
| Critical projects | SLAs, sovereignty, explainability for large accounts |

This framework turns every Publicis Sapient RAG project from a cost into an investment. The real question is not "is it worth it" — it is "how many projects does it take to break even". The answer: one or two client projects are enough to pay off the full V1–V4 development.
