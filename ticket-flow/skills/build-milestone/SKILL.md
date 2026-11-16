---
name: build-milestone
description: Builds ONE milestone of a planned ticket in one session - test first, then the code, then the proof, then an independent strict code review, then the tick. Use when the user says "build M1", "next milestone", "continue the ticket" or "start building", or opens a ticket that has an approved plan and an open milestone. Also use when review findings come back, before ticking a milestone or saying anything is done or fixed, and when the last milestone is ticked and the ticket must be closed with the creator. Adapted from obra/superpowers (MIT, © 2025 Jesse Vincent).
argument-hint: <milestone ID, or the creator's reply to the result>
---

# Build milestone

One milestone, one session. Test first, code, proof, an independent review, then the tick.
Then stop.

## Rules for the whole skill

- **ONE milestone per session.** When it is ticked, stop. The next one starts in a new
  session. Why: a fresh session reads the plan again instead of trusting its memory, each
  review covers one small piece, and the dashboard card stays true.
  A hook holds this line: code can be written only with an approved plan and an open
  milestone, and after the tick only notes (`.md` files) can be written in this session.
- **No code without a failing test first.**
- **No "done" and no tick without fresh proof.** If you did not run the check in this message,
  you cannot say it passes.
- **No tick on a code milestone without a review.** There is no way to skip it.
- Never weaken or delete a test to make it pass.
- Tests never touch a live system. Build a tiny made-up copy of the data instead.
- Build only what the milestone says. A new idea goes on a list for the engineer, not into
  the code.
- Talk in plain, simple words. When the engineer must do something: ONE step, then wait.
- The ticket's `CLAUDE.md`, and `MY_DEFAULTS.md` if there is one in the project folder or the
  folder above it, say how this team lays out, runs and logs its code. Follow them.

## Step 0: where are we?

Read `requirements.md`, `PLAN.md` and `tracking_log.md`. Take the first row that fits.

| What you find | Do this |
|---|---|
| Status is not `CONFIRMED BY CREATOR` | Stop. The next step is the `ticket-flow:clear-ticket` skill. |
| No milestone lines, or no `Plan approved by` line | Stop. The next step is the `ticket-flow:plan-milestones` skill. |
| `requirements.md` has a `## Closed` section | The ticket is closed, and stays closed. Say so, and stop. A new wish is a new ticket with its own folder: it starts there, with `ticket-flow:clear-ticket`. |
| A milestone was already ticked in this session | Stop. Tell the engineer to start a new session for the next one. |
| Every milestone is ticked, and `## Now working on` in `tracking_log.md` says `waiting for <name> to confirm the result` | The result is already with the creator. Go to "Closing the ticket", Part 2, and ask the engineer for the reply. |
| Every milestone is ticked | Nothing was sent yet. Go to "Closing the ticket", Part 1. |
| The first open milestone is already built: the newest line under `## Last update` in `tracking_log.md` says `M<n> built, tests pass, waiting for review` | Do not build it again. Go to Step 3 and get the whole proof again: run the suite, and ask for a user check again if "Done when" has one. An earlier session's proof does not count. Then go to Step 4. The files to review: with `.git`, the changed files in the folder; without it, the files listed in `.claude/review-files.txt`. |
| There is an open milestone | Take the FIRST open one. Tell the engineer which one it is and what its "Done when" says. |

Only when you took the last row (there is an open milestone to build), check these three
things before you start. In every other row, skip them.

- **Leftover changes.** If the folder has `.git`, run `git status`. Changed files from before
  this session would get mixed into this milestone's review. Tell the engineer what is there
  and ask what to do with it. Do not start until that is settled.
- **Too big?** Read the milestone's section in `PLAN.md`. If it will not fit in one session,
  stop and split it (M3a, M3b) by the rules in `ticket-flow:plan-milestones`. The engineer
  approves the split. Then build the first half.
- **The log.** If `## Now working on` in `tracking_log.md` names another milestone, or still
  says the ticket waits for the creator to confirm the result, fix it: it names the milestone
  you are about to build.

## Step 1: which kind of milestone is it?

| Its "Done when" says | Kind | What to do |
|---|---|---|
| Named tests | Code | Steps 2, 3, 4, 5, 6 |
| `user check — ...` and no code is written | Check only | Step 3, then Step 6. No review: there is no code to review. |
| Both | Code | Steps 2, 3, 4, 5, 6 |

If a "check only" milestone turns out to need code, it is a code milestone. All steps apply.

## Step 2: test first, one behaviour at a time

Follow the milestone's steps in `PLAN.md`.

1. **Write one test** for one behaviour, with the name from `PLAN.md` and the exact values
   from `requirements.md`. Use the real code and small made-up sample data.
2. **Run it and watch it fail.** It must fail because the behaviour is missing, not because
   of a typo or a bad import. If it passes at once, it tests something that already works:
   change the test.
3. **Write the smallest code** that makes it pass. No options "for later".
4. **Run the WHOLE suite**, not only the new test. Report every failure by name, even one
   you did not cause.
5. **Tidy up** names and repeats while the suite stays green. No new behaviour here.
6. Next behaviour: back to 1.

If you wrote code before its test, delete that code and start again from the test. Do not
keep it "for reference".

A bug you meet on the way: first a test that shows the bug and fails, then the fix. The test
stays, so the bug cannot come back.

If the plan turns out to be wrong (a step that cannot work, a missing piece), stop and tell
the engineer. Fix the plan together by the rules in `ticket-flow:plan-milestones`, then carry
on. Never quietly build something other than what the plan says.

## Step 3: prove it

Read the milestone's "Done when" and get exactly that proof.

| "Done when" says | The proof | Then |
|---|---|---|
| Named tests pass | Run the whole suite now. Read all of the output: those tests exist and pass, nothing fails, no errors. | Quote the result, for example "6 passed". |
| `user check — ...` | Give the engineer numbered steps to check it themselves: what to open or run, and what they should see. One step at a time. | Wait for them to say it worked. No answer, or "not yet", is not a pass. |
| Both | Both. Tests first. | |

These are not proof:

- an earlier run, or "should pass now", "looks right", "probably"
- a test that passes for another milestone
- another agent saying it worked: run the tests yourself
- green tests, when "Done when" asks for a user check

If the proof fails, say what really happened, with the output. Then fix it or ask. Do not go on.

## Step 4: the independent review (code milestones)

The reviewer is a separate agent that has never seen this session. It can only read. It
judges the code, not your reasons.

1. **Collect what changed.**
   - With `.git`: for each new file, by name, run `git add -N <file>` (never a data file or
     a file with logins). Then save the changes to a file with
     `git diff HEAD --output=.claude/review.diff`. Make the `.claude` folder first if it is
     not there.
   - Without `.git`: save the list of files this session made or changed in
     `.claude/review-files.txt`, one path per line. If the file is already there, an earlier
     session of this milestone wrote it: keep its lines and add yours. A later session cannot
     know what this one changed, so the list must be in a file. If you picked the milestone up
     from an earlier session and the file is missing, ask the engineer which files belong to
     this milestone.
2. **Start a fresh `ticket-flow:code-reviewer` agent.** Give it only these:
   - the path of the diff file, or the list of changed files from `.claude/review-files.txt`
   - the milestone ID, and the paths of `PLAN.md` and `requirements.md`

   Never give it your reasoning, a description of what you built, a note that the tests pass,
   or a hint about what to skip. It must judge from the code alone.
3. **Read the whole review** before you do anything.

If the reviewer cannot be started (the plugin's agent is missing, an error, no budget left):
do not review your own code and call that a review. The milestone stays open. Add under
`## Last update` in `tracking_log.md`:
`YYYY-MM-DD — M<n> built, tests pass, waiting for review: <why it could not run>`.
Tell the engineer, and stop.

If the engineer asks to skip the review, say no kindly and say why: the tick means "proved
and reviewed", and it is worth nothing if it sometimes means less. Then offer what does help:
the milestone waits as it is, with the line above in the log, until a review can run.

## Step 5: the findings

`VERDICT: PASS` with no findings: go to Step 6.

Otherwise, first check each finding against the real code. A finding is a claim, not an
order: find the line and see if the problem really happens.

Then tell the engineer about all of them in ONE message, numbered. For each one:

- what is wrong, in plain words, and where
- why it matters: what would happen to a real person using this
- what the fix would change
- if you believe the finding is wrong: say so, with facts (the file, the line, a test). No opinions.

Mark a DESIGN finding as "a question about the approach". It is the engineer's call, and
their answer may change the code.

End with one question: "Which ones do I fix? Say 'all', or the numbers."

Then wait. Fix nothing before the answer.

For each finding the engineer wants fixed, one at a time:

1. Write a test that shows the bug, and watch it fail. If it passes, it does not show the bug
   yet. If the bug cannot be shown in a test, tell the engineer and ask how to go on.
2. Fix only that bug. Run the whole suite.

For each finding the engineer does NOT want fixed, add under `## Last update` in
`tracking_log.md`: `YYYY-MM-DD — M<n> review: not fixed (<the finding, short>): <their reason>`.
Never drop a finding silently.

Then review again:

- Make a new diff, the same way as in Step 4. Without `.git`, add the files the fixes made
  or changed to `.claude/review-files.txt`.
- Start a NEW reviewer, never the old one. Give it the new diff or list, the same three paths, and
  the earlier findings copied word for word.
- If it reports again a finding the engineer already chose not to fix, do not ask a second
  time. It is in the log.

One round is: the fixes, then one fresh review. If there are still new findings after two
rounds, stop. Tell the engineer plainly where things stand and ask what to do: another round,
split the milestone, or think the approach over. No tick while that is open.

If the session ends with the milestone still open, add under `## Last update` in
`tracking_log.md`:
`YYYY-MM-DD — M<n> built, tests pass, waiting for review: findings still open after 2 rounds`.
The next session reads that line in Step 0 and starts at the review, not at the first test.

## Step 6: close the milestone

Only when the proof is in hand and, for a code milestone, the review has passed or every
finding is fixed or logged. In this order:

1. If any code changed since Step 3, run the whole suite once more.
2. Tick it in `requirements.md`: `- [x] M<n> — ...`. This one line only.
3. In `tracking_log.md`, add under `## Last update`:
   `YYYY-MM-DD — M<n> ticked, <proof>, <review>`, for example
   `2026-11-18 — M2 ticked, 6 tests pass, review passed after 1 fix round`.
   For a check-only milestone the last part is `no code, no review`.
   Put the next open milestone under `## Now working on` and the one after it under
   `## Next up`.
4. If the folder has `.git`, commit only what was looked at:
   - Delete `.claude/review.diff`.
   - Add by name the files that were in the review, and `requirements.md`, `tracking_log.md`
     and `PLAN.md` (and `CLAUDE.md` if you changed it): `git add <file> <file> ...`. Never
     add everything at once.
   - Run `git status`. Any other new or changed file was not reviewed, so do not add it. Tell
     the engineer which file it is and ask: does it belong to this milestone (then it goes
     through the review first), or should git leave it alone (then add a line for it to
     `.gitignore`)? Data files and files with logins are always left alone.
   - `git commit -m "M<n> — <what it delivers>"`. Never push.

   If the folder has no `.git`, delete `.claude/review-files.txt`, so the next milestone
   starts its own list.
5. If that was the last milestone, do part 1 of "Closing the ticket" now.
6. Tell the engineer what was done and what comes next. Then STOP. The next milestone starts
   in a new session.

## Closing the ticket

Every milestone is ticked. The ticket is done when the creator says the result solves their
problem, or when the engineer tells you the ticket is done.

**Part 1: show the creator.** Write a message for the engineer to paste. Short and plain:

- the real issue, in one line, as the creator confirmed it
- what version 1 does now, following the Then lines of the contract
- how they can see it for themselves
- what waits for later, from the fence
- last line: "Does this solve it? Reply yes, or tell me what is missing."

In `tracking_log.md`, set `## Now working on` to
`PENDING (creator, YYYY-MM-DD): waiting for <name> to confirm the result.`

If the folder has `.git`, commit this edit by name, so the next session does not find it
as a leftover change: `git add tracking_log.md`, then
`git commit -m "Result sent to the creator"`. Never push. Then stop.

**Part 2: the reply.** The engineer brings it, pasted or in their own words. That is their
call, as in clear-ticket. If it was not pasted, ask once: "Did they add any 'but' or any
extra wish?"

| What comes back | What it is | Do this |
|---|---|---|
| "Yes", "Works, thanks" | A real yes | Close the ticket (below). |
| "Yes, but can it also ..." | Version 1 is fine, and there is a new wish | Close the ticket. The wish is new work: a new ticket with its own folder, which starts there with `ticket-flow:clear-ticket`. Say so to the engineer. |
| "It does not do X", and X is in the contract | Not done | Add a milestone for X by the rules in `ticket-flow:plan-milestones`. In `tracking_log.md`, take out the PENDING line and put the new milestone under `## Now working on`. If the folder has `.git`, commit the files you changed, by name, with `git commit -m "M<n> added"`. Build the milestone in a new session. |
| "It does not do X", and X is not in the contract | A new wish, not a fault | The same as "yes, but". Ask the creator if version 1 does what was agreed. |
| The engineer says "the ticket is done" | The engineer closes it | Close the ticket, and write that the engineer said so. |

**Close the ticket:**

1. Add at the end of `requirements.md`. The Status line stays as it is.

   ```markdown
   ## Closed
   > <the creator's exact words, when the engineer pasted them>
   (<name>, <where: Slack, Jira comment, email, call>, <date>)
   ```

   No paste: in place of the quote line write `Told by <engineer>: <what the creator said>`.
   Closed by the engineer: write `Closed by <engineer> (<date>): <what they said>`.
2. In `tracking_log.md`: take out the PENDING line, write `Ticket closed` under
   `## Now working on` and `Nothing` under `## Next up`, and add under `## Last update`:
   `YYYY-MM-DD — ticket closed, confirmed by <name>`.
3. If the folder has `.git`: add the files you just changed, by name
   (`git add requirements.md tracking_log.md`, and `CLAUDE.md` if `git status` shows it
   changed), then `git commit -m "Ticket closed"`. Never push.
4. Tell the engineer the ticket is closed. Stop.

## Stop and start over when

- you wrote code before its test
- a new test passed the first time you ran it
- you cannot say why a test failed
- you are about to write "done", "fixed" or "works" without a run in this message
- you think "too simple to test", "I'll add the test after" or "just this once"

## Common mistakes

| Mistake | Do this instead |
|---|---|
| Starting the next milestone "because there is time" | One per session. Stop. |
| Ticking in the same message as a code change, with no run after it | Run the suite, then tick |
| Telling the reviewer what you did or why it is right | The diff and the three paths, nothing else |
| Sending fixes back to the same reviewer | A new one every time |
| Fixing a finding before the engineer answered | One message with all findings, then wait |
| Fixing a bug with no test that shows it | The failing test comes first |
| Fixing more than the finding ("while I'm here") | Only that bug |
| Leaving out a finding the engineer said no to | It goes in the log, with their reason |
| Reviewing your own code when the reviewer cannot run | The milestone waits, and the log says why |
| Ticking a user check the engineer has not confirmed | Wait for their answer |
| Committing every file in the folder at once | Only the reviewed files and the three md files, by name |
| Taking a new wish for a fault in version 1 | Check it against the contract |
