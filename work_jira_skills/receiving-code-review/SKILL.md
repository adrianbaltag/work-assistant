---
name: receiving-code-review
description: Use in Phase 4-Review of a work_jira ticket when review findings arrive (from /code-review, feature-dev:code-reviewer, /simplify, or the user) - check each finding against the real code before changing anything, push back on wrong ones, fix one at a time with tests. Adapted from obra/superpowers (MIT, © 2025 Jesse Vincent).
---

# Receiving Code Review (work_jira)

## Overview

A review finding is a claim to check, not an order. Check it, then fix it or push back with reasons.

## For every list of findings

1. **Read all of them** before changing anything.
2. **Say each one back** in one plain line. Unclear? Ask about it first, before fixing ANY of
   them: findings are often linked.
3. **Check it against the real code:** does the problem actually happen? Find the line, or write a
   test that shows it.
4. **Decide:** fix, push back, or ask the user.
5. **Fix one at a time,** in this order: wrong results or data risk → small fixes (typos, imports)
   → bigger rewrites. Run the test suite after each fix.
6. **Report** what you changed, where, and what you rejected and why.

## Push back when

- the fix would break something that works (show the test)
- the reviewer missed context: Spyder `# %%` layout, the `test=True` switch, read-only Z:/Y:,
  Python 3.10 at work, a helper from RESOURCES.md used on purpose
- it adds a feature nobody uses ("make it configurable", "add CSV export"): search the code for
  a caller first, and if there is none, propose dropping it
- it goes against a decision the user already made: stop and ask the user

Push back with facts (file, line, test), not opinions.

## Answering

- Correct finding → just fix it: "Fixed: blank site IDs are skipped now (read_sites, test_skips_blank_rows)."
- Wrong finding → "Not changed: <reason, with file/line or test>."
- Can't verify → "I can't check this without <X>. Should I look into it, or skip it?"
- You pushed back and were wrong → "Checked again, you're right: <why>. Fixing."
- No "Great point!", "You're absolutely right!" or thanks. The fix shows you listened.

## Where findings go

Findings you don't fix (rejected, or accepted by the user as-is) go in tracking_log.md, one line
each with the reason. Phase 4→5 needs every finding fixed or accepted by the user.
