---
name: writing-plans
description: Use in Phase 2-Plan of a work_jira ticket, after the user approved the requirements and before any code - turns requirements.md into milestone lines (in requirements.md) plus a step-by-step PLAN.md. Adapted from obra/superpowers (MIT, © 2025 Jesse Vincent).
---

# Writing Plans (work_jira)

## Overview

Turn the approved requirements into milestones someone could build without guessing. Write down
what you decided: which files, which function names, which values from ticket.md, which tests or
user checks prove each milestone. Leave out what any reasonable Python developer would do anyway.

**Announce at start:** "I'm using the writing-plans skill to write the milestones and PLAN.md."

**Only plan. Write no code and no tests in this session.**

## Where the plan goes

| What | Where | Format |
|------|-------|--------|
| Milestones | `requirements.md`, in its milestones section (add `## Milestones` only if there is none) | one line each, see below |
| Steps per milestone | `PLAN.md` in the ticket folder | one `### M1 — …` section per milestone |

Never write plans anywhere else (no `docs/` folder).

## Milestone lines

```markdown
- [ ] M1 — read the site list from the input sheet · Done when: test_reads_site_list, test_skips_blank_rows pass
- [ ] M2 — prod copy runs in Spyder · Done when: user check — test=True run in Spyder shows the summary table
```

Rules (the milestone hooks read these lines):
- Exactly `- [ ] M<number> — <what it delivers> · Done when: <proof>`. Sub-milestones: M3a, M3b.
- Proof = named pytest tests that pass (code milestone), OR `user check — <what the user looks at>`
  (review, Spyder run, prod).
- **No `<angle brackets>` in a real line.** The hooks treat any line with `<…>` as template text and skip it.
- Each milestone fits in ONE session. Too big → split it (M3a, M3b) now, not later.
- Each milestone ends with something the user can see working, or with named tests going green.

## PLAN.md sections

One section per milestone, numbered steps, each step one action with a checkable result:

```markdown
### M1 — read the site list from the input sheet

Files: `site_report.py` (function `read_sites(path, test=False) -> list[dict]`), `tests/test_site_report.py`

1. Write test `test_reads_site_list`: sample sheet in `tests/data/` → 3 dicts with keys site_id, market.
2. Run `python -m pytest tests -v` → it fails (function missing).
3. Write `read_sites` in its own `# %%` cell.
4. Run the tests → all pass.
5. Same for `test_skips_blank_rows`.
```

A step names: the test and what it asserts (with exact values from ticket.md), OR the function
signature and file, OR the command and the output that means it passed. A step that decides nothing
("handle edge cases", "add tests", "TBD") is a gap: fix it.

## Ticket rules every plan follows

- Prod script layout: Spyder-safe `# %%` cells, a `__main__` guard, a `test=True` switch for Spyder runs.
- Z: and Y: are read-only: the plan never writes there. Prod copies are done by the user by hand.
- work_jira has no git: no commit steps.
- Read `RESOURCES.md` (work_jira root) first and reuse its prod helpers instead of planning new ones.

## Self-review (do it yourself, then fix inline)

1. **Coverage:** every requirement in requirements.md has a milestone. List any gap.
2. **Steps:** each step lets the builder do exactly one reasonable thing. No step writes the whole function body.
3. **Names:** function names and signatures match across milestones.
4. **Risky inputs:** the 3–5 inputs most likely to break it for a real user (blank cell, missing file,
   odd site ID…). Each one gets a test in the milestone that owns the code.
5. **Size:** PLAN.md much longer than the code it describes = you wrote the code. Cut to signatures and tests.

## Hand-off

Tell the user: "Milestones are in requirements.md and the steps in PLAN.md. Please review them."
Wait for their approval. When approved: set Phase to 3-Build in the ticket CLAUDE.md, put M1 under
`## Now working on` and M2 under `## Next up` in tracking_log.md, then STOP. Building starts in a new session.
