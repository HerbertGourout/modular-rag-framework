# Archive

Documents moved out of active navigation, most on 2026-08-06 (documentation-utility pass,
follow-up to the 2026-08-06 documentation audit — itself archived here as of 2026-08-07, see
the last row below). Nothing here is deleted or rewritten — each file is kept verbatim (or, for
the ADR, verbatim-plus-its-existing-banner) as a historical record, with Git history intact via
`git mv`. If you're looking for **current, active** guidance, none of these five files is it —
follow the pointer in each entry below instead.

| File | What it was | Why archived | Current guidance instead |
|---|---|---|---|
| [0004-strategic-features-v1-v5.md](0004-strategic-features-v1-v5.md) | ADR-0004 — the original 8-feature, V1→V5 native-build plan (666 lines) | Superseded (partial) by ADR-0005 since 2026-08-04; kept in `docs/adr/` at full length anyway, likely to be skimmed and misread despite the banner | [ADR-0005](../adr/0005-document-ai-control-plane-boundary.md) — a short stub remains at the original `docs/adr/0004-strategic-features-v1-v5.md` path, pointing here |
| [feature-integration-plan.md](feature-integration-plan.md) | Commercial/staffing plan: deal-size and revenue figures per V1-V5 feature | Figures were computed before ADR-0005's delegation pivot changed the delivery model for 4 of the 8 features; no longer a reliable basis for a current commercial decision | [business-case.md](../business-case.md) for the current commercial argument |
| [working-with-agents.md](working-with-agents.md) | 561-line guide to building a native multi-agent runtime | Already carried a "superseded by ADR-0005" banner; the underlying design (coordinator/planner/retriever/synthesizer/validator agents) was removed as dead code in Lot 17 | [docs/refactoring/lot-17-prototype-retirement.md](../refactoring/lot-17-prototype-retirement.md) for what replaced it (delegation via the `DocumentEngine` port) |
| [2026-05-20-initial-review.md](2026-05-20-initial-review.md) | A one-time historical review of the project at an early, near-empty scaffold state | Correctly dated and scoped already, but zero ongoing operational relevance | [docs/refactoring/README.md](../refactoring/README.md) for what actually happened since |
| [documentation-audit-2026-08.md](documentation-audit-2026-08.md) | The 6-part documentation audit deliverable (inventory, quality diagnostic, structure analysis, update plan, cleanup recommendations, 22-item P0-P4 checklist) that produced this whole `docs/archive/` directory and most of the 2026-08-06 documentation-accuracy fixes across the repo | Point-in-time audit record — the fixes it recommended are long since applied; keeping it in active navigation invited readers to treat a snapshot as a live task list | This file's own table (above) for what was archived as a result, and `git log` for the individual fix commits it drove |

None of these five were found factually wrong in the 2026-08-06 audit — they were accurate (or
correctly banner-flagged) but low-utility: long, easy to mistake for current guidance, and each
has a shorter, current document that supersedes it in practice. Archiving is a navigation
decision, not a correction.
