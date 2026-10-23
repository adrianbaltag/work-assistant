---
name: verification-before-completion
description: Use in a work_jira ticket before ticking a milestone box or saying anything is done, fixed or passing - show the proof the milestone's "Done when:" asks for (fresh pytest output, or the user confirming their check) first. Adapted from obra/superpowers (MIT, © 2025 Jesse Vincent).
---

# Verification Before Completion (work_jira)

## The rule

```
NO "DONE" AND NO TICKED BOX WITHOUT FRESH PROOF
```

If you didn't run the check in this message, you can't say it passes.

## Find the proof: read the milestone's "Done when:"

| "Done when:" says | Proof you need | Then |
|---|---|---|
| named tests pass | Run `python -m pytest tests -v` now. Read the whole output: those tests pass, 0 failures, no errors. | Tick, quote the result (e.g. "6 passed") |
| `user check — …` | Give the user numbered steps to check it themselves (exact Spyder cell, file, what they should see). Wait for their reply. | Tick only after they say it worked. No reply or "not yet" = leave it unticked |
| both | Both, tests first | Tick after both |

Tests failing or user says it's wrong → don't tick. Say the real state with the evidence, and fix
or ask.

## Not proof

- An earlier run, or "should pass now", "looks right", "probably"
- A test passing for a different milestone
- A subagent saying it succeeded: open the files and run the tests yourself
- Tests green when "Done when:" asks for a user check

## Red flags: stop

- About to write "Done!", "Fixed!", "Works!" before running anything
- Ticking a box in the same message you changed code, without a test run after the change
- "Just this once"

## After the tick

Follow the end-of-milestone steps in work_jira CLAUDE.md (tracking_log.md lines, Phase, then STOP).
One milestone per session: don't start the next one.
