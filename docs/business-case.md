# Business case — Portable Document AI Assurance Framework

**Status:** Working hypothesis, not a validated sales claim
**Last reviewed:** 2026-09-01

## Executive summary

The framework should be evaluated as a reusable assurance and delivery layer for Document AI
solutions, not as another competitor to LangChain, LangGraph, LlamaIndex, Haystack, or cloud AI
platforms. Its proposed value is to make governance requirements portable and testable across
those runtimes while providing a native reference RAG engine for local-first delivery and
conformance.

The current repository already demonstrates useful foundations: contract-driven adapters,
manifest validation, tenant isolation, policy enforcement, redaction, durable audit, offline
evaluation, feedback, human review, drift signals, and engine selection. It does **not** yet prove
that all controls work uniformly around an existing third-party application. That remaining gap
is central to the next product phase.

No delivery-time saving, margin improvement, or break-even point is asserted here as fact. Those
outcomes must be measured in pilots against a comparable baseline.

## 1. Customer problem

Enterprise teams increasingly operate more than one Document AI stack: bespoke Python services,
LangChain/LangGraph applications, cloud-managed retrieval services, and platform-specific model
gateways. Each stack may expose its own tracing or evaluation tools, but delivery teams still
need consistent answers to cross-cutting questions:

- Which identity and tenant were allowed to access which evidence?
- Which data was permitted to leave the deployment boundary and for which provider?
- Which citations, policy decisions, and model-usage facts support an answer?
- Which checks are enforced, merely observed, or unavailable for this engine?
- Can the same acceptance suite be run before switching engine or cloud platform?
- Can feedback, review, and drift evidence be compared across projects?

The commercial problem is therefore fragmentation of assurance and delivery practice, not lack
of an orchestration library.

## 2. Proposed value proposition

> Apply a portable, evidence-backed assurance contract to Document AI solutions, whether they use
> the native reference engine or an existing external application.

The useful combination is:

1. declarative solution and policy configuration;
2. fail-closed capability negotiation;
3. identity, tenant, redaction, and provider-egress controls;
4. normalized audit, provenance, quality, cost, feedback, and review evidence;
5. conformance suites that state the achieved assurance level;
6. a native reference implementation that can run independently of a cloud platform.

None of these individual features is unique. The hypothesis is that packaging them as a portable
delivery standard, with honest cross-engine guarantees, reduces repeated integration and
qualification work.

## 3. Where it complements existing platforms

| Existing choice | What it already does well | Proposed role of this framework |
|---|---|---|
| LangChain / LangGraph | Application composition, agents, tools, durable graph workflows, ecosystem integrations | Wrap an existing application; add portable policy/evidence contracts and cross-project conformance without replacing its graph. |
| LlamaIndex / Haystack | Retrieval and Document AI composition, connectors, evaluation or pipeline primitives | Normalize assurance evidence and delivery controls where the adapter can observe or intercept them. |
| Cloud AI platforms | Managed identity, networking, model access, observability, evaluation, and platform-native governance | Integrate with—not replace—those controls; provide a cloud-neutral contract and comparable acceptance evidence. |
| Native framework engine | Inspectable sequential RAG, local composition, reference semantics | Serve as the reference implementation and local/offline-first option, not the only supported runtime. |

The framework is unnecessary when one platform's native controls fully satisfy the organization,
portability is not required, and no reusable cross-project standard is desired.

## 4. Target users and engagements

The strongest initial users are:

- platform teams standardizing multiple RAG or Document AI applications;
- security and governance teams that need explicit evidence boundaries;
- delivery teams reusing policies, manifests, tests, and adapters across clients;
- regulated or multi-tenant projects where unsupported controls must fail before deployment;
- organizations that must support local, on-premise, or multiple-cloud execution.

It is a weaker fit for a short-lived, single-tenant prototype where direct use of an existing
library is simpler and there is no reuse or assurance requirement.

## 5. Product packages to validate

Potential service offerings, subject to pilot validation:

- **Document AI assurance assessment:** map an existing application to L0/L1/L2, identify missing
  evidence and controls, and produce a remediation plan.
- **Governed delivery baseline:** deploy the native or an external adapter with approved
  manifests, tests, audit, and data-egress policy.
- **Cross-engine qualification:** run the same conformance profile against two execution options
  before a migration or sourcing decision.
- **Operational assurance:** connect feedback, review, drift, quality, and cost evidence to the
  client's operational process.

These are service hypotheses, not commitments that the current pre-alpha package can deliver
without deployment-specific engineering.

## 6. Evidence required before commercial claims

Each pilot should record at least:

| Measure | Baseline | Framework evidence |
|---|---|---|
| Time to first governed deployment | Comparable delivery without the framework | Person-days by activity, including adapter and policy work |
| Reuse | Components copied or rebuilt between projects | Unchanged manifests, policies, tests, and adapters reused |
| Control coverage | Required controls and manual checks | Enforced, observed, unsupported, and bypass-tested controls |
| Portability | Effort to change engine/provider | Code, configuration, test, and operational changes required |
| Quality regression detection | Existing release process | Regressions caught before release and false-positive rate |
| Operational burden | Incidents and maintenance effort | Adapter failures, upgrade work, and evidence-store operations |

Only measured results should later support statements such as “weeks saved,” margin uplift, or
break-even after a given number of projects.

## 7. Commercial and licensing caveats

The repository is distributed under Apache License 2.0. Whether an organization also owns
proprietary accelerators, deployment assets, policies, or services built around it depends on
their actual authorship and distribution model; the open-source package itself should not be
described generically as proprietary IP.

Compliance must also be framed carefully: software can enforce controls and produce evidence,
but it does not by itself certify GDPR, HIPAA, CCPA, or another regulatory regime. Jurisdiction
must come from deployment, contractual, residency, identity, and legal context—not inferred from
the language of a user query.

## 8. Investment priorities

Before expanding orchestration breadth, investment should prioritize:

1. provider data-classification and deny-by-default egress controls (Lot 20);
2. an engine-independent assurance/capability contract and conformance report;
3. wrapping an existing LangChain/LangGraph application without rebuilding it;
4. uniform audit, policy, review, feedback, usage, and provenance evidence where hooks permit;
5. two or more measured pilots that test reuse and integration cost.

The accepted direction is recorded in
[ADR-0015](adr/0015-portable-assurance-and-external-application-boundary.md). Priorities 1 and 2
are implemented: provider egress control ships (Lot 20,
[ADR-0016](adr/0016-provider-egress-control.md)) and so does the engine-independent assurance
contract with its conformance report (Lot 21,
[ADR-0017](adr/0017-engine-independent-assurance-contract.md)). Priority 3 exists only as a
contract (Lot 22, [ADR-0018](adr/0018-existing-application-adapter-boundary.md)): no adapter, no
selectable manifest, so no application can be wrapped today. Priorities 4 and 5 remain open, and
the pilots in priority 5 are what the decision gate below depends on.

## Decision gate

Continue investing in the product thesis only if pilots show both:

- material reuse or assurance value beyond the selected platform's native tooling; and
- an integration burden low enough that wrapping an existing application is preferable to
  project-specific governance code.

If those conditions are not met, keep the native engine as an internal reference accelerator and
avoid positioning the package as a general cross-platform product.
