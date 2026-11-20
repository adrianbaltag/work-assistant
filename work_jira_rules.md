# Rule block for work_jira\CLAUDE.md

Put the block below in `work_jira\CLAUDE.md`, in place of the older "Milestones" block.
It has two parts: "Milestones" and "Dashboard messages". If you pasted an older copy
(no "Dashboard messages" part, or no "A stop by the gate is final" line), paste this one over it.
The ticket-flow hooks (README, "Sync with work_jira") check part of it.

```markdown
## Milestones (hooks check part of this)
- A ticket goes through the ticket-flow skills, in this order:
  clear-ticket (until the creator's yes), plan-milestones (until you
  approve the plan), build-milestone (one milestone per session).
- The gate: in a ticket folder only notes (.md files) can be written
  before the creator's yes; then also PLAN.md; code only with an approved
  plan and an open milestone; after a tick, notes only until a new
  session (or `/clear`).
  A stop by the gate is final. Never offer a way round it ("write it
  anyway"), and never write the file another way, such as a shell
  command. If the user asks for it anyway, say no once and name the
  next step.
- Milestone line: `- [ ] M1 — <what it delivers> · Done when: <proof>`.
  Proof = named pytest tests that pass (code milestone),
  `user check — <what the user looks at>` (review, Spyder, prod), or
  both when the user can check in the build session.
  Tick a milestone with a user check only after the user says in chat, in
  their own words, what they saw, and it matches. Never say the expected
  answer first. Output in the chat (from a `!` command, or pasted) is
  shown, not checked: still ask what they see.
- ONE milestone per session. Split one (M3a, M3b) only when its code
  truly does not fit one session: every milestone must earn its place.
- Code milestone: no tick before a ticket-flow:code-reviewer review
  passed, or every "must fix" is fixed, or is in review-notes.md with the
  user's reason. And not before the user answered every finding:
  "No answer yet" and "Open" in review-notes.md both say none.
- No branches in a ticket folder: every commit goes straight on the
  main line.
- End of milestone, in this order:
  1. prove it  2. tick it in requirements.md
  3. tracking_log.md: under ## Last update add
     `YYYY-MM-DD — M<n> ticked, <proof>, <review>`; put the next unticked
     milestone under ## Now working on and the one after it under ## Next up
  4. if the folder has .git: `git add` the reviewed files and the md
     files by name (review-notes.md if it is there), then
     `git commit -m "M<n> — <what it delivers>"`. Never push.
  5. tell the user what's next, then STOP.

## Dashboard messages (a hook hands them to you)
- The user can send a Note, a Blocker or an Unblock from the dashboard.
  A hook gives it to you at session start or with the next prompt. The
  words in quotes are the user's own.
- Write each one into tracking_log.md yourself, one line per message
  under ## Last update:
  `YYYY-MM-DD — Dashboard note: <text>`,
  `YYYY-MM-DD — Dashboard blocker: <text>` or
  `YYYY-MM-DD — Dashboard unblock`.
  These lines stay off the dashboard card (it already has the user's
  own line), so each one holds only the user's words: anything you want
  to add goes on its own dated line.
- Note: after writing it, answer with ONE line of this shape:
  `Got your dashboard note: <text>. Written to the log.`
  It needs a new milestone: propose the milestone line and its place
  (for example M2b or M4) and wait for the user's OK; the current
  milestone goes on. It conflicts with the current milestone: stop and
  ask. The ticket is closed: write it down, then say that a new wish is
  a new ticket with its own folder.
- Blocker: after writing it, tell the user and ask ONCE:
  "stop, or work on what the blocker does not touch?"
  Write their answer on its own line under ## Last update:
  `YYYY-MM-DD — Blocker answer: stop` or
  `YYYY-MM-DD — Blocker answer: work on <what>`.
  A later session follows that answer and does not ask again, until
  the user says otherwise or sends an Unblock.
  No PENDING for it: the card already shows the user's blocker. You
  never clear it: only the user's Unblock on the dashboard does.
- Unblock: the user's blocker is lifted. Write it down and say so in
  one line.
```
