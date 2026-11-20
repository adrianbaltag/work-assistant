---
name: build-milestone
description: Builds ONE milestone of a planned ticket in one session - test first, then the code, then the proof, then an independent strict code review, then the tick. Use when the user says "build M1", "next milestone", "continue the ticket" or "start building", or opens a ticket that has an approved plan and an open milestone. Also use when review findings come back, before ticking a milestone or saying anything is done or fixed, and when the last milestone is ticked and the ticket must be closed with the creator. Adapted from obra/superpowers (MIT, © 2025 Jesse Vincent).
argument-hint: <milestone ID, or the creator's reply to the result>
---

# Build milestone

One milestone, one session: test first, code, proof, an independent review, the tick. Then stop.

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
- **No branches in a ticket folder.** Every commit goes straight on the main line (the
  folder's one branch, `main` or `master`). A ticked milestone is one commit. Never make,
  switch, merge or delete a branch by yourself, even when the engineer's own rules say that
  work goes on a branch. A folder that is already on another branch: Step 0 says what to do.
- **This plugin decides the steps in a ticket folder:** plan, review, tick, commit, close. The
  engineer's own rules, skills and agents for planning, reviewing, committing or closing work
  stay quiet here: do not run them on top of these steps. Their rules for HOW code is written
  (logging, code checks such as ruff, style) still count.
- The ticket's `CLAUDE.md`, and `MY_DEFAULTS.md` if there is one in the project folder or the
  folder above it, say how this team lays out, runs and logs its code. Follow them.

## Step 0: where are we?

Read `requirements.md`, `PLAN.md` and `tracking_log.md`. Take the first row that fits.

| What you find | Do this |
|---|---|
| Status is not `CONFIRMED BY CREATOR` | Stop. The next step is the `ticket-flow:clear-ticket` skill. |
| No milestone lines, or no `Plan approved by` line | Stop. The next step is the `ticket-flow:plan-milestones` skill. |
| `requirements.md` has a `## Closed` section | The ticket is closed, and stays closed. Say so, and stop. A new wish is a new ticket with its own folder: it starts there, with `ticket-flow:clear-ticket`. |
| A milestone was already ticked in this session | Stop. Tell the engineer to start a new session (or `/clear`) for the next one. |
| Every milestone is ticked, and `## Now working on` in `tracking_log.md` says `waiting for <name> to confirm the result` | The result is already with the creator. Go to "Closing the ticket", Part 2, and ask the engineer for the reply. |
| Every milestone is ticked | Nothing was sent yet. Go to "Closing the ticket", Part 1. |
| The first open milestone is already built: the newest line under `## Last update` in `tracking_log.md` says `M<n> built, tests pass, waiting for review`, or `review-notes.md` has a block for it | Do not build it again. Go to Step 3 and get the whole proof again: run the suite, and ask for a user check again if "Done when" has one. An earlier session's proof does not count. Then: if `review-notes.md` has a block for this milestone, the full review is done, so go to "Picked up from an earlier session" in Step 5. No block: the full review never ran, so go to Step 4. The files to review: with `.git`, the changed files in the folder; without it, the files listed in `.claude/review-files.txt`. |
| There is an open milestone | Take the FIRST open one. Tell the engineer which one it is and what its "Done when" says. |

**The branch.** Whichever row you took, unless it told you to stop: if the folder has `.git`,
run `git status` before anything else. Its first line names the branch. `main` or `master`: go
on. Anything else: do nothing by yourself. Tell the engineer which branch the folder is on
and what is on it that the main line does not have (`git log main..HEAD --oneline` lists
those commits; say `master` if that is the main line's name), and ask what to do. Do not go
on until that is settled. Then do what the engineer says: switching, merging or deleting a
branch is their call, never yours. Why: work that sits only on that branch must not be left
behind, or moved, without the engineer.

Only when you took the last row (there is an open milestone to build), check these three
things before you start. In every other row, skip them.

- **Leftover changes.** If the folder has `.git`, run `git status`. Changed files from before
  this session would get mixed into this milestone's review. Tell the engineer what is there
  and ask what to do with it. Do not start until that is settled.
- **Too big?** Read the milestone's section in `PLAN.md`. Only if it truly will not fit in one
  session, stop and split it (M3a, M3b) by the rules in `ticket-flow:plan-milestones`. The
  engineer approves the split. Then build the first half.
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
| `user check — ...` | The engineer does the looking, by the rules in "A user check" below: you show where to look, they say what they see. | Wait for their answer, then compare. No answer, or "not yet", is not a pass. |
| Both | Both. Tests first. | |

**A user check.** The engineer's own eyes are the proof, so the engineer does the looking. In
every user check, whatever it checks (a count, a value, a file, a screen, a list of changes):

1. Show what to look at: what to open or run, and where to look. One step at a time.
2. Ask an open question: "What do you see there?", "How many rows do you count?"
3. Never say the expected answer first, and never count it, read it off or sum it up for
   them. After "you should see 12 rows, right?" the engineer can only say yes, and that yes
   proves nothing.
4. Compare only after their answer. It fits what `requirements.md`, the tests or the script's
   own output say: a pass. It does not: say what was expected, and take it as a failed proof
   (below).

These are not proof:

- an earlier run, or "should pass now", "looks right", "probably"
- a test that passes for another milestone
- another agent saying it worked: run the tests yourself
- green tests, when "Done when" asks for a user check
- the engineer's "yes" to an answer you said first: ask again, with an open question

If the proof fails, say what really happened, with the output. Then fix it or ask. Do not go on.

## Step 4: the independent review (code milestones)

The reviewer is a separate agent that has never seen this session. It can only read. It
judges the code, not your reasons. This first review is full and strict: it reads
everything the milestone changed. A review after it only checks the repairs (Step 5).

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

   Say nothing about how risky the job is. The reviewer works that out itself, from the
   `RISKY:` line in `requirements.md` and from what the code does. Do not ask the engineer
   about it either.
3. **Read the whole review** before you do anything. It has a `RISK:` line, a `MUST FIX`
   list, a `GOOD TO KNOW` list, and a last line: `VERDICT: PASS` or `VERDICT: FIX`.

If the reviewer cannot be started (the plugin's agent is missing, an error, no budget left):
do not review your own code and call that a review. The milestone stays open. Add under
`## Last update` in `tracking_log.md`:
`YYYY-MM-DD — M<n> built, tests pass, waiting for review: <why it could not run>`.
Tell the engineer, and stop.

If the engineer asks to skip the review, say no kindly and say why: the tick means "proved
and reviewed", and it is worth nothing if it sometimes means less. Then offer what does help:
the milestone waits as it is, with the line above in the log, until a review can run.

## Step 5: the findings

| List | What is in it | The tick |
|---|---|---|
| `MUST FIX` | A real case ("with this input, this wrong thing happens") and one of four reasons: a wrong result, a broken promise to the creator, harm to a live system (in every job: a test that reads a live system), a secret | Waits until it is fixed, or the engineer says no and gives a reason |
| `GOOD TO KNOW` | Everything else: weak spots, and doubts with no real case | Does not wait. The engineer sees these once and picks. |

`VERDICT: PASS` means `MUST FIX` is empty. There can still be notes under `GOOD TO KNOW`.

The reviewer sorts by how risky the job is. So the same weak spot can be a "must fix" in a
job that changes a live system, and "good to know" in a job that only reads. Never move a
finding to the other list yourself.

**Write it down first.** As soon as a review comes back,
before you tell or ask the engineer anything, put what it found in `review-notes.md`, beside
`requirements.md` (make the file if it is not there). A later session goes on from it, so a
break loses nothing. One block per milestone, also when the review found nothing:

   ```markdown
   # Review notes

   What the code reviews found, and what happened to it. One block per milestone.

   ## M<n> (YYYY-MM-DD)
   Repair checks so far: 0

   No answer yet (the engineer has not said what to do):
   - MUST FIX: <the finding, word for word>
   - GOOD TO KNOW: <the finding, word for word>

   Open (picked for repair, not past a repair check yet):
   - MUST FIX: <the finding, word for word>
   - GOOD TO KNOW: <the finding, word for word>

   Left as it is (the engineer's choice):
   - GOOD TO KNOW: <the finding, word for word>
   - MUST FIX: <the finding, word for word>. Reason (<engineer>): <their reason>
   ```

- A new finding goes under "No answer yet", word for word, with the reviewer's heading.
- The engineer's answer moves it: to "Open" if they picked it, to "Left as it is" if not.
  A "must fix" goes there with their reason: if they gave none, ask for it once.
- "Left as it is" is settled: never ask again, also when a later review reports it again.
- A finding leaves "Open" when a repair check says `FIXED`. A small "good to know" fix that
  needs no new review (the table below) leaves it when the whole suite passes.
- A list with nothing in it says `none`.

No finding gets its own line in `tracking_log.md`. The log gets one line, at the tick
(Step 6). Never drop a finding silently.

`VERDICT: PASS` and no notes: go to Step 6.

**Tell the engineer.** First check each finding against the real code. A finding is a claim,
not an order: find the line and see if the problem really happens.

Then tell the engineer about all of them in ONE message, numbered. The "must fix" ones come
first, under their own heading. Then the "good to know" ones. For each one:

- what is wrong, in plain words, and where
- why it matters: what would happen to a real person using this
- what the fix would change
- if you believe the finding is wrong, or is in the wrong list: say so, with facts (the file,
  the line, a test). No opinions.

A finding that starts with `Approach:` is a doubt about the way the code is built. It is in
one of the two lists like any other finding. Say that it is about the approach: fixing it
may change more than one line.

A finding can say that the code changes something live and `requirements.md` has no
`RISKY:` line. Then the job turned out risky. Never add a `RISKY:` line yourself to settle
it. Stop and tell the engineer that the job turned out risky. The plan changes first, by
the rules in `ticket-flow:plan-milestones` ("Changing the plan later"): it gets its dry run.

Say which ones hold the tick and which do not. End with one question: "Which ones do I fix?
Say 'all', or the numbers."

Then wait. Fix nothing before the answer. This is the only time the engineer is asked about
the "good to know" notes: a later review adds no new ones. When the answer comes, move each
finding in the block before you repair anything.

**Repair what the engineer picked.** (A session that picked the milestone up stages nothing
and checks the whole milestone: see the last part of this step.)

1. If the folder has `.git`, first stage the files the last review looked at, by name:
   `git add <file> <file> ...` (never a data file or a file with logins, never everything
   at once). After a repair check, those are the files its repairs touched. Stage
   `review-notes.md` too. From here on, a plain `git diff` shows only the repairs.
2. Take the picked findings one at a time:
   - Write a test that shows the problem, and watch it fail. If it passes, it does not show
     the problem yet. If the problem cannot be shown in a test, tell the engineer and ask
     how to go on.
   - Fix only that. Run the whole suite.

**Does it need a new review?**

| What you repaired | Then |
|---|---|
| At least one "must fix" | A repair check (below). |
| Only "good to know" notes, and every fix stayed small | No new review. Go to Step 6. |
| Only "good to know" notes, and a fix grew | A fix grew when it adds new behaviour, or touches a code file the note does not name (its own test does not count). Tell the engineer that it grew, and why. Then a repair check (below). |
| Nothing | Go to Step 6. |

**The repair check.** It does not review the milestone again. It checks only the repairs: is
each old finding really fixed, and did a repair break something?
If `Repair checks so far` says 2 or more, ask the engineer first, as the stop rule says.

- With `.git`: for each new file a repair made, by name, run `git add -N <file>`. Then save
  only the repairs: `git diff --output=.claude/review.diff`. There is no `HEAD` in it this
  time, so it leaves out what you staged.
- Without `.git`: add the files the repairs made or changed to `.claude/review-files.txt`.
  The reviewer gets only those files this time, not the whole list.
- Start a NEW reviewer, never the old one. Give it only these:
  - the words "Repair check"
  - the "Open" list from `review-notes.md`, copied word for word, each finding under the
    heading it had (`MUST FIX`, `GOOD TO KNOW` or `REPAIR NOTES`)
  - the path of the diff file, or the list of the files the repairs touched
  - the milestone ID, and the paths of `PLAN.md` and `requirements.md`

As soon as it comes back, before anything else, bring the block up to date:
add 1 to `Repair checks so far`. Take each `FIXED` finding off. Move each `NOT FIXED` one to
"No answer yet", with what the reviewer says still goes wrong. Put what is new there too.

What comes back:

| It says | What it means |
|---|---|
| `FIXED` | The old finding is gone, and its test would catch it if it came back. |
| `NOT FIXED` | The old finding is still there. It keeps the heading it had. |
| `broken by a repair` under `MUST FIX` | Something worked before the repair and does not now, with a real case and one of the four reasons. A "must fix". |
| `new, outside the repairs` | A new "must fix" the reviewer ran into. It adds no new "good to know" notes. |
| `REPAIR NOTES` | A repair broke something that fits none of the four reasons. It does not hold the tick. The engineer sees it and picks, as with a "good to know" note. |

- Nothing is under "No answer yet": go to Step 6.
- Something is: tell the engineer in one message, as above, and move each finding by their
  answer. After `VERDICT: PASS` none of it holds the tick, and what they pick is repaired
  like any "good to know" note. After `VERDICT: FIX` it is the next round, if the stop rule
  below allows one. Both start at step 1 of "Repair what the engineer picked".

One round is: the repairs, then one repair check. So a milestone gets three reviews at most:
the full one and two repair checks, in one session or in several. After two rounds (the
block says `Repair checks so far: 2` or more), start no repair check on your own,
whatever is open. If a repair check would be next, or a "must fix" is still open, stop.
Tell the engineer plainly where things stand and ask what to do:
another round, split the milestone, or think the approach over. If findings wait for an
answer too, ask both in ONE message: the findings, then this question. No tick while a
"must fix" is open. "Another round" is one round: ask again after every extra round.

If the session ends with the milestone still open, add under `## Last update` in
`tracking_log.md`:
`YYYY-MM-DD — M<n> built, tests pass, waiting for review: <N> findings open in review-notes.md`.
The block already holds every finding, so nothing else has to be saved.

**Picked up from an earlier session.** Step 0 sends you here when `review-notes.md` has a
block for this milestone. The full review is done: do not run it again. Trust nothing an
earlier session staged or knew about files. In this order:

1. Something is under "No answer yet": tell the engineer and move each finding by their
   answer, as in "Tell the engineer". Never repair a finding the engineer did not pick.
   If `Repair checks so far` says 2 or more, the stop rule's question goes in the same message.
2. For each finding under "Open", see if its repair is there: a test that shows the problem,
   and it passes. If not, repair it now, test first. Stage nothing in this session: skip
   step 1 of "Repair what the engineer picked".
3. Then run a repair check, whatever the table above says, also when "Open" says `none`:
   the code may have changed since the last review, by hand or in Step 3 of this session.
   If `Repair checks so far` says 2 or more, ask the engineer first, as the stop rule says.
   When the check comes back, go on at "As soon as it comes back" above.

Every repair check in this session, the first one too, gets the WHOLE milestone:

- With `.git`: `git add -N` each new file, by name, then
  `git diff HEAD --output=.claude/review.diff`, as in Step 4. If `git status` shows an
  untracked code or test file you did not make, ask the engineer first if it belongs to
  this milestone.
- Without `.git`: add the files this session made or changed to `.claude/review-files.txt`,
  then give it the whole list.
- In place of the words "Repair check", say: "Repair check on a picked-up milestone. This
  holds the whole milestone, not only the repairs. Check only these findings."

## Step 6: close the milestone

Only when the proof is in hand and, for a code milestone, the review is settled: the last
review said `VERDICT: PASS`, or every "must fix" is fixed or is under "Left as it is" in
`review-notes.md` with the engineer's reason. In the milestone's block there,
"No answer yet" and "Open" both say `none`. A "good to know" note never holds the tick.
In this order:

1. If any code changed since Step 3, run the whole suite once more.
2. Tick it in `requirements.md`: `- [x] M<n> — ...`. This one line only.
3. In `tracking_log.md`, add ONE line under `## Last update`:
   `YYYY-MM-DD — M<n> ticked, <proof>, <review>`. The last part says how the review ended,
   and how many findings of this milestone are under "Left as it is" in `review-notes.md`:
   - `2026-11-18 — M2 ticked, 6 tests pass, review passed after 1 fix round`
   - `2026-11-18 — M1 ticked, 23 tests pass, review passed, 4 notes in review-notes.md`
   - `2026-11-18 — M3 ticked, 9 tests pass, review: 1 must fix not fixed, 2 notes in review-notes.md`

   For a check-only milestone the last part is `no code, no review`.
   Put the next open milestone under `## Now working on` and the one after it under
   `## Next up`.
4. If the folder has `.git`, commit only what was looked at:
   - Delete `.claude/review.diff`.
   - Add by name the files that were in a review, and `requirements.md`, `tracking_log.md`
     and `PLAN.md`. Also `review-notes.md` if it is there, and `CLAUDE.md` if you changed it:
     `git add <file> <file> ...`. Never add everything at once. A new test file made for a
     small "good to know" fix (Step 5) goes in too.
   - Run `git status`. Any other new or changed file was not reviewed, so do not add it. Tell
     the engineer which file it is and ask: does it belong to this milestone (then it goes
     through the review first), or should git leave it alone (then add a line for it to
     `.gitignore`)? Data files and files with logins are always left alone.
   - `git commit -m "M<n> — <what it delivers>"`, straight on the main line: no branch.
     Never push.

   If the folder has no `.git`, delete `.claude/review-files.txt`, so the next milestone
   starts its own list.
5. If that was the last milestone, do part 1 of "Closing the ticket" now.
6. Tell the engineer what was done and what comes next. Then STOP. The next milestone starts
   in a new session (or `/clear`).

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
extra wish?" The engineer's own project (the yes in `requirements.md` says `own project`):
there is no creator, so skip this question.

| What comes back | What it is | Do this |
|---|---|---|
| "Yes", "Works, thanks" | A real yes | Close the ticket (below). |
| "Yes, but can it also ..." | Version 1 is fine, and there is a new wish | Close the ticket. The wish is new work: a new ticket with its own folder, which starts there with `ticket-flow:clear-ticket`. Say so to the engineer. |
| "It does not do X", and X is in the contract | Not done | Add a milestone for X by the rules in `ticket-flow:plan-milestones`. In `tracking_log.md`, take out the PENDING line and put the new milestone under `## Now working on`. If the folder has `.git`, commit the files you changed, by name, with `git commit -m "M<n> added"`. Build the milestone in a new session (or `/clear`). |
| "It does not do X", and X is not in the contract | A new wish, not a fault | The same as "yes, but". Ask the creator if version 1 does what was agreed. |
| The engineer says "the ticket is done" | The engineer closes it | Close the ticket, and write that the engineer said so. |

**Close the ticket:**

1. Add at the end of `requirements.md`. The Status line stays as it is.

   ```markdown
   ## Closed
   Pasted:
   > <the creator's exact words>
   (<name>, <where: Slack, Jira comment, email, call>, <date>)
   ```

   No paste: in place of the first two lines write `Told by <engineer>: <what the creator said>`.
   Closed by the engineer: write `Closed by <engineer> (<date>): <what they said>`.
   These three are the only labels, and the lines say only what really happened. Never write
   that something was checked or ruled out ("confirmed, no but") unless you asked it in this
   chat and the engineer answered. Then add their answer as a line of its own:
   `Asked about a "but": <the engineer's answer>`.
2. In `tracking_log.md`: take out the PENDING line, write `Ticket closed` under
   `## Now working on` and `Nothing` under `## Next up`, and add under `## Last update`:
   `YYYY-MM-DD — ticket closed, confirmed by <name>`. When the engineer closed it, the line
   is `YYYY-MM-DD — ticket closed by <engineer>`.
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
| Telling the reviewer what you did, why it is right, or how risky the job is | The diff and the three paths. In a repair check also the old findings, word for word. Nothing else. |
| Sending fixes back to the same reviewer | A new one every time |
| Running the full review again after a repair, or in a new session | Only the first review is full. The next ones are repair checks on the findings in `review-notes.md`. |
| Holding the tick for a "good to know" note | Only a "must fix" holds the tick |
| Moving a finding to the other list yourself | The reviewer sorts. If you disagree, tell the engineer why, with facts. |
| Fixing a finding before the engineer answered | One message with all findings, then wait |
| Asking about the "good to know" notes a second time | Once. What is not fixed is in `review-notes.md`. |
| Fixing more than the finding ("while I'm here") | Only that bug |
| Leaving out a finding the engineer said no to | It goes in `review-notes.md`. A "must fix" goes there with their reason. |
| Reviewing your own code when the reviewer cannot run | The milestone waits, and the log says why |
| Saying what a user check should show, then asking "right?" | Show where to look, ask what they see, compare after their answer |
| Making a branch for a milestone | No branches in a ticket folder. Commit on the main line. |
| Finding the folder on another branch, and switching back or merging by yourself | Say which branch and what is on it, and ask. The engineer decides. |
| Running the engineer's own planning, review or closing skill as well | The plugin decides the steps. Their rules for how code is written still count. |
| Committing every file in the folder at once | Only the reviewed files and the ticket's md files (`review-notes.md` too), by name |
| Taking a new wish for a fault in version 1 | Check it against the contract |
| Writing "confirmed, no but" when nobody asked | Only what happened. A check goes in the file only if you asked it and the engineer answered. |
