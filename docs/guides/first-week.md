# Your First Week

A five-day programme that turns the reference documentation into something you have actually run.
Each day ends with evidence you produced yourself — a report file, a command output, a failing
check you made fail on purpose — not with a page you read.

It assumes nothing but a machine, a clone, and Docker. Work through it in order: each day uses
what the previous one installed or built.

## What costs money, and what does not

Almost all of this runs on free, local, deterministic components. Two adapters ship specifically
so that the pipeline can be exercised with no model download and no provider account:
`DeterministicEmbedder` and `DeterministicGenerator`. The days below use them.

| Tier | What it needs | Used on |
|---|---|---|
| Offline | Nothing — no service, no key, no network | Days 1, 4, 5 |
| Qdrant | A local Qdrant container on `:6333` | Days 2 and 3 |
| Qdrant + PostgreSQL | Both containers, still no provider key | Day 3 |
| Paid provider | A real `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | Optional only, never required |

Every exercise marked **optional (paid)** can be skipped without breaking a later day. Nothing in
the five days depends on data that is not in this repository.

## Before day 1

Install the framework by following **steps 1 to 7** of [installation.md](installation.md)'s
clean-room checklist. That guide calls those seven the deterministic part, and they are exactly
what this programme requires: no external service and no paid credential. Skipping one is the most
common reason a day below fails for a reason that has nothing to do with the exercise.

Its remaining steps are not prerequisites here. Step 8 starts Qdrant, which days 2 and 3 need and
which the next paragraph covers. Steps 9 and 10 export a provider key and run the provider-backed
first query; they belong to the optional exercises only, and no day below depends on them.

Install Docker as well. You will need two containers, both official images, both discarded at the
end of the week:

```bash
docker run -d --name mrag-qdrant -p 6333:6333 qdrant/qdrant
docker run -d --name mrag-postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
```

Start them on the day that needs them, not now.

---

## Day 1 — What this is, and proof that it runs

**Goal.** Understand what the product claims, learn where the truth about it is recorded, and get
a working installation that proves itself without any external service.

**Read.**

- [docs/onboarding.md](../onboarding.md), the prerequisite concept map and sections 3 and 5.
  Section 5 is the one to take seriously: it lists what must not be promised.
- [architecture/capability-matrix.md](../architecture/capability-matrix.md) — the per-capability
  truth, with evidence.
- [glossary.md](../glossary.md), sections 1 and 8. Section 8 tells you which words this project
  refuses to use, and why.

**Do.** Everything here runs offline.

```bash
.venv\Scripts\python.exe -m pytest tests/unit tests/contract -q
.venv\Scripts\python.exe scripts/check_layering.py
.venv\Scripts\python.exe scripts/check_docs.py
.venv\Scripts\mrag.exe version
.venv\Scripts\mrag.exe validate manifests/presets/local-hybrid-rag.yaml
```

Then make one of them fail deliberately. Copy the preset, delete its whole `governance:` block, and
validate the copy:

```bash
.venv\Scripts\mrag.exe validate <your-copy>.yaml
```

**Evidence.**

- A passing unit and contract run, `Layering check passed.`, and `Docs check passed.`
- `OK: manifests\presets\local-hybrid-rag.yaml is valid (schema version 1.0, id=local-hybrid-rag)`
- From the copy, an `INVALID` exit naming the real reason: `generator type 'openai' is a known
  remote provider, but no governance.egress_policy is configured to cover it`.

**You are done when** you can say, without looking it up, what that last error protects against —
and why the framework refuses at startup rather than at the first request.

---

## Day 2 — How a document becomes an answer

**Goal.** Follow one question end to end, in the code and then in a real run.

**Read.**

- [code-walkthrough.md](code-walkthrough.md) — the guided tour, levels 0 to 5.
- [architecture/runtime-flow.md](../architecture/runtime-flow.md) — the sequence diagrams,
  including the egress checkpoints.
- [architecture/data-model.md](../architecture/data-model.md) — `Document`, `Chunk`, `Query`,
  `Answer`, `Citation`.

**Do.** Start Qdrant, then run the offline benchmark. It wires a complete pipeline with a
deterministic embedder and generator, so it needs no provider key and downloads no model:

```bash
docker start mrag-qdrant
.venv\Scripts\python.exe scripts/run_benchmark.py
```

Open the report it writes to `src/modular_rag/eval/reports/latest.md`.

Then do the tracing exercise on paper. Take any component role in
`manifests/presets/local-hybrid-rag.yaml` and follow it through three hops: the manifest key, the
factory that builds it in `app/default_factories.py`, and the class that factory instantiates.
Repeat for the chunker, the retriever and the generator.

**Evidence.**

- `latest.md` and `latest.json`, both keyed by your current commit.
- A three-column note of your own — manifest key, factory line, class — for at least three roles.
- The complete execution sequence, written out in order from
  [architecture/runtime-flow.md](../architecture/runtime-flow.md) and then checked against
  `orchestration/engine.py`. It spans two functions, so check both: `RAGEngine._run_steps()` holds
  the inner pipeline, from the tenant-policy check through human review and the
  assurance-evidence recording that closes it, and its caller
  `RAGEngine._run()` holds what happens once that returns — the root span's outcome, the trace
  handed to telemetry, the `RUN_SUCCEEDED` or `RUN_FAILED` audit event, and the final state
  transition. Include the provider-egress checkpoints, which sit between stages rather than being
  stages of their own. Do not work from a remembered number of steps: the sequence is conditional,
  and the count depends on what the manifest wires.

**Optional (paid).** Run a real hybrid query against a provider by following
[getting-started.md](getting-started.md), which uses a single process so that the in-memory BM25
leg and the persistent Qdrant leg are both live.

**You are done when** you can name which stages disappear entirely when their component is not
configured — `local-hybrid-rag.yaml` wires no security or governance component, so most of them do
— and which run on every request regardless.

---

## Day 3 — What the framework refuses to do

**Goal.** See the governance controls act, rather than read that they exist.

**Read.**

- [architecture/security.md](../architecture/security.md) and
  [architecture/data-classification-policy.md](../architecture/data-classification-policy.md).
- [glossary.md](../glossary.md), sections 3 to 5 — security, governance and evidence, assurance.
- [ADR-0016](../adr/0016-provider-egress-control.md), [ADR-0017](../adr/0017-engine-independent-assurance-contract.md)
  and [ADR-0018](../adr/0018-existing-application-adapter-boundary.md), in that order.

**Do.** Start both containers, then run the deterministic governance scenario. It exercises tenant
isolation, redaction, policy-as-code and a durable audit trail, and it deliberately needs no
provider key:

```bash
docker start mrag-qdrant mrag-postgres
.venv\Scripts\python.exe -m pytest tests/e2e/test_secure_preset_e2e.py -v -m e2e
```

Note what the test actually loads. Its fixture renders
`tests/e2e/manifests/secure-deterministic-rag.yaml`, not the production preset — see
`tests/e2e/_secure_preset_fixtures.py`. Read that deterministic manifest alongside the test and
pair each of its five `governance:` keys with the assertion that proves it.

Then run the comparison that matters. Diff the two governance blocks:

```bash
.venv\Scripts\python.exe -c "import yaml; d=yaml.safe_load(open('tests/e2e/manifests/secure-deterministic-rag.yaml',encoding='utf-8')); p=yaml.safe_load(open('manifests/presets/secure-enterprise-rag.yaml',encoding='utf-8')); print(sorted(set(p['governance'])-set(d['governance'])))"
```

Three keys come back — `egress_policy`, `feedback_sink` and `review_queue`. The production preset
declares them and this test does not exercise them. That gap is the point of the exercise: a
passing governance suite is evidence about the controls it loads, never about the controls it
omits.

Then read `contracts/assurance.py` and answer one question in writing: why can an adapter not
declare its own assurance level?

**Evidence.**

- A passing deterministic e2e run.
- A list pairing each of the deterministic manifest's five `governance:` keys with the assertion
  that proves it.
- The three-key gap above, written down as what this suite does *not* prove.
- Your written answer on `achieved_level`, checked against the module docstring.

**You are done when** you can state, without hedging, which parts of Lot 22 exist today and which
do not — and point at the file that settles it.

---

## Day 4 — How work actually gets delivered here

**Goal.** Learn the two-provider delivery workflow before you need it, not during your first
review.

**Read.**

- [ai-engineering-workflow.md](ai-engineering-workflow.md) — the bounded chat workflow and its
  vocabulary. This is the authority on the sequence.
- [model-routing.md](model-routing.md) — which work needs which review.
- [validation-protocol.md](validation-protocol.md) — the tiers, the CI mapping, and the difference
  between a failed, a skipped and an unavailable check.
- [CLAUDE.md](../../CLAUDE.md) section 04.

**Do.** Everything here runs offline.

Take a change you have not made — for instance, adding one unit test to an existing test module —
and write a complete handoff for it in a scratch copy of `.review/handoff.example.md`. Fill every
section: immutable base, acceptance criteria, design decisions, validation executed and
unavailable, known limitations, out of scope.

Then work through the tier table in [validation-protocol.md](validation-protocol.md) and record
which tiers are available to you today. Run the two that need nothing:

```bash
.venv\Scripts\ruff.exe check src/modular_rag tests
.venv\Scripts\python.exe -m pytest tests/unit tests/contract -q
```

Those are what the quick and full tiers wrap. Both platforms have a script that chains a whole
tier for you, and `CONTRIBUTING.md`'s own checklist names both:

```bash
./scripts/check.sh full                                    # Linux, macOS
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1 full   # Windows
```

Use the tier your task requires, which is a question `validation-protocol.md` answers and habit
does not.

**Evidence.**

- A handoff with no empty section, including an honest "unavailable" entry for anything you cannot
  run.
- A note of which tiers ran, which were skipped for a missing service, and which you could not run
  at all — using those three words in the sense `validation-protocol.md` defines.

**You are done when** you can explain why the review loop stops after two passes, and what the one
bounded remediation after pass 2 may and may not do.

---

## Day 5 — A real contribution, up to the pull request

**Goal.** Take one bounded change through the project's actual rules, stopping just before the
delivery decision, which is not yours to make alone.

**Read.**

- [CONTRIBUTING.md](../../CONTRIBUTING.md), and specifically the recipes table: find the row for
  the change type you are about to make.
- [documentation-style-guide.md](documentation-style-guide.md) if your change touches any
  Markdown.

**Do.** Pick a change that has a row in the recipes table, and let that row — not your judgement of
what seems sufficient — decide what the change requires. Two rows suit a first contribution:

- **Documentation only**, for a troubleshooting entry covering an error you hit this week, or a
  correction to something this programme told you that turned out to be wrong. That last one is
  the most valuable change you can make in week one.
- **Bug fix**, if you found a real defect. Its row requires the failing test *first*, written
  before the fix.

There is no recipe row for adding a test on its own, so do not invent one. A test that belongs to
a bug fix travels under the bug-fix row.

Now execute your row end to end.

```bash
git checkout -b <type>/<short-description>
# make the change, following the row's "Before you start" and "Files it touches" columns
```

Run the row's **Mandatory validation** column, in full. For the documentation-only row that is
`scripts/check_docs.py` and `git diff --check`. For the bug-fix row it is your targeted test, then
the full gate:

```bash
./scripts/check.sh full                                    # Linux, macOS
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1 full   # Windows
```

Apply the row's **Documentation impact** and **Review** columns too. Review follows risk: check
your change against [model-routing.md](model-routing.md), and if it calls for a review, prepare the
handoff the way you practised on day 4 before asking for one.

Then commit, using the conventional format `CONTRIBUTING.md` defines:

```bash
git add <the files your row names>
git commit
git log -1 --stat
```

Finally, work through the **Pull Request Checklist** in `CONTRIBUTING.md` and fill the
PR-description template it contains. Do not push and do not open the pull request: that is the
delivery decision, and it is not yours alone to make in your first week.

**Evidence.**

- A branch whose name matches the conventions in `CONTRIBUTING.md`.
- A green run of the mandatory validation named by your recipe row — in full, not a tier you chose
  because it was fast.
- A local commit, visible in `git log -1 --stat`, with an atomic conventional message.
- A handoff, if your row's review column called for one.
- The Pull Request Checklist worked through line by line, and the PR description drafted from the
  template — including `docs/ updated if applicable`, which you answer either way.

**You are done when** someone else can read your branch, your commit message and your checklist,
and reconstruct what you changed and why without asking you.

---

## Optional deeper tracks

Take one of these in week two, chosen by what you will actually work on. None is a prerequisite
for the others.

### Architecture

[ADR-0001](../adr/0001-modular-architecture.md) and [ADR-0002](../adr/0002-contracts-and-plugins.md),
then [architecture/module-model.md](../architecture/module-model.md) and
[document-engine-contract.md](../architecture/document-engine-contract.md). Exercise: add a
component through [plugin-development.md](plugin-development.md) and register it in a manifest of
your own, without wiring anything in Python.

### Security and governance

[ADR-0003](../adr/0003-security-and-governance.md), then
[architecture/threat-model.md](../architecture/threat-model.md) and
[postgres-permissions.md](postgres-permissions.md). Exercise: configure an egress policy that
denies a classification level, and prove it denies by observing the decision rather than by
reading the code.

### Evaluation

[offline-evaluation.md](offline-evaluation.md), then `eval/datasets/core_v1.yaml`. Exercise: add a
case to the golden set, rerun the benchmark, and explain the metric movement — including whether
the quality gate would treat it as a regression.

### Operations

[deployment.md](deployment.md), [backup-restore.md](backup-restore.md) and
[observability.md](observability.md). Exercise: enable the OTel tracer and meter roles in a
manifest of your own and confirm that no shipped preset enables them, and why.

---

## When this guide is wrong

It will be, eventually. The authority order in [docs/onboarding.md](../onboarding.md), section 1.1,
settles every conflict: executable code, manifests, tests and CI first, accepted ADRs and contracts
second, and guides — including this one — below both. If a command here does not behave as
described, the command is right and this page is the thing to fix.
