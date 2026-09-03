# Lot 22 — Existing-Application Adapters and Cross-Engine Conformance

**Status:** PLANNED — depends on completed Lots 20–21

**Priority:** P1 after the assurance contract

**Indicative size:** L–XL (3–5 weeks), time-box the first application spike

## Purpose

Prove that the framework adds value to a team that already has a LangChain/LangGraph application.
The application must be wrapped without reconstructing its internal graph from framework
components, then assessed at the assurance level its available hooks genuinely support.

## Required scope

1. Select one sanitized, representative existing LangChain/LangGraph application with retrieval,
   generation, streaming or tools, and real citations/evidence where available.
2. Define a thin application-adapter interface that accepts framework execution context and
   returns normalized result/evidence without exposing vendor-native types to callers.
3. Preserve the application's graph, state, prompts, tools, checkpoints, and deployment ownership;
   the adapter must not silently replace them with the repository's fixed LangGraph graph.
4. Apply Lot 20 egress policy before any framework-owned outbound handoff. Document which internal
   application egresses can be intercepted and which require client-side hooks.
5. Negotiate and report the achieved L0/L1/L2 level. A lower level is acceptable; an overstated
   level is not.
6. Exercise synchronous, asynchronous, streaming, cancellation, tool-call, partial-failure, and
   retry behavior applicable to the selected application.
7. Compare integration effort and evidence coverage against using the application's native
   platform tooling alone.
8. Publish an adapter-author guide and a second fake/reference adapter fixture to show that the
   contract is not specific to one client graph.

## Security requirements

- no raw prompt, context, secret, pseudonym map, or restricted content in audit/conformance output;
- identity and tenant context cannot be replaced by untrusted application metadata;
- a tool or nested model call cannot bypass a control that the adapter claims is enforceable;
- streaming must not emit content before required pre-output checks for the declared level;
- missing hooks reduce the declared assurance level or reject the profile; they never become a
  silent allow.

## Non-goals

- supporting every LangChain/LangGraph version or integration in the first lot;
- migrating client code to the native engine;
- rebuilding a client graph using framework component factories;
- claiming parity where the external application exposes only opaque input/output hooks;
- building adapters for every cloud provider before the first pilot is measured.

## Acceptance evidence

- the representative application runs unchanged internally behind the adapter;
- the Lot 21 conformance report is produced and its claimed level passes all mandatory checks;
- negative bypass, cross-tenant, egress, streaming, tool-call, and partial-failure tests pass;
- unsupported controls are visible before deployment;
- measured person-days, changed application lines, reusable assets, and residual platform-specific
  work are recorded against the native-tooling baseline;
- a human architecture/security decision confirms whether the pilot justifies further adapters.

## Decision gate

Do not generalize the adapter programme unless the pilot demonstrates meaningful assurance or
reuse beyond the selected platform's native capabilities at acceptable integration cost. If it
does not, retain the native engine and assurance contracts as an internal accelerator rather than
claiming a general external-application product.
