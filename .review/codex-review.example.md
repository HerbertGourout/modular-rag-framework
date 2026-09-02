# Codex Review

## Status

PENDING

## Review identity

- Review pass: `1/2` | `2/2`
- Review mode: `DISCOVERY` | `CLOSURE_ONLY`
- Base commit:
- Implementation checkpoint:
- Corrective base (pass 2 only):
- Task:
- Premium reason, if any:

## Acceptance criteria checked

- [ ]

## Finding closure (pass 2 only)

| Previous finding | Resolution claimed | Verification | Result |
|---|---|---|---|
| | | | `CLOSED` / `OPEN` |

## BLOCKER

## HIGH

## MEDIUM

## LOW

## Validation performed

## Remaining risks

List only risks that affect the human validation decision. Accepted or deferred
risks must retain that disposition and must not be reopened without new evidence.

## Summary

Use the following structure for each material finding. Do not create findings
merely to populate a severity section.

### <ID> — <title>

Severity: BLOCKER | HIGH | MEDIUM | LOW
Disposition: MUST_FIX | FIX_IN_SCOPE | DEFERRED | ACCEPTED_RISK
File: path/to/file.py
Location: line, symbol, or affected area

Problem:
...

Impact:
...

Evidence:
...

Recommended action:
...

On pass 2, a new finding is valid only when the corrective diff introduced it.
Record that causal evidence explicitly. `READY_FOR_FINAL_VALIDATION` ends the
Codex review loop even when non-blocking findings or residual risks remain.
