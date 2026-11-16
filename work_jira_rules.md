# Rule block for work_jira\CLAUDE.md

Put the block below in `work_jira\CLAUDE.md`, in place of the older "Milestones" block.
The ticket-flow hooks (README, "Sync with work_jira") check part of it.

```markdown
## Milestones (hooks check part of this)
- A ticket goes through the ticket-flow skills, in this order:
  clear-ticket (until the creator's yes), plan-milestones (until you
  approve the plan), build-milestone (one milestone per session).
- The gate: in a ticket folder only notes (.md files) can be written
  before the creator's yes; then also PLAN.md; code only with an approved
  plan and an open milestone; after a tick, notes only until a new session.
- Milestone line: `- [ ] M1 — <what it delivers> · Done when: <proof>`.
  Proof = named pytest tests that pass (code milestone) OR
  `user check — <what the user looks at>` (review, Spyder, prod).
  Tick a user-check milestone only after the user confirms in chat.
- ONE milestone per session. Too big → split (M3a, M3b) before starting.
- Code milestone: no tick before a ticket-flow:code-reviewer review
  passed, or every finding is fixed or listed in tracking_log.md.
- End of milestone, in this order:
  1. prove it  2. tick it in requirements.md
  3. tracking_log.md: under ## Last update add
     `YYYY-MM-DD — M<n> ticked, <proof>, <review>`; put the next unticked
     milestone under ## Now working on and the one after it under ## Next up
  4. if the folder has .git: `git add` the reviewed files and the md
     files by name, then `git commit -m "M<n> — <what it delivers>"`.
     Never push.
  5. tell the user what's next, then STOP.
```
