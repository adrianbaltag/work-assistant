# Rule block for work_jira\CLAUDE.md

Put the block below in `work_jira\CLAUDE.md`, in place of the old "End of milestone" sentence.
The milestone hooks (README, "Sync with work_jira") check part of it.

```markdown
## Milestones (hooks check part of this)
- Milestone line: `- [ ] M1 — <what it delivers> · Done when: <proof>`.
  Proof = named pytest tests that pass (code milestone) OR
  `user check — <what the user looks at>` (review, Spyder, prod).
  Tick a user-check milestone only after the user confirms in chat.
- ONE milestone per session. Too big → split (M3a, M3b) before starting.
- Code milestone: run /code-review low on its files before the session
  ends; fix the findings or list them in tracking_log.md.
- End of milestone, in this order:
  1. prove it  2. tick it in requirements.md
  3. tracking_log.md: under ## Last update add
     `YYYY-MM-DD — M<n> ticked, <proof>`; put the next unticked milestone
     under ## Now working on and the one after it under ## Next up
  4. if the phase changed, update Phase in the ticket CLAUDE.md
  5. if the folder has .git: `git add .` then
     `git commit -m "M<n> — <what it delivers>"`. Never push.
  6. tell the user what's next, then STOP.
- Phase changes: 1→2 requirements approved by user · 2→3 milestones
  written and approved · 3→4 all build milestones ticked · 4→5 review
  findings fixed or accepted by user.
```
