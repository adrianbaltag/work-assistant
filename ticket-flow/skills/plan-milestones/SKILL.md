---
name: plan-milestones
description: Turns a ticket the creator has confirmed into milestones, each small enough for one session and each with a proof. Use after clear-ticket is done (requirements.md says CONFIRMED BY CREATOR), whenever the user says "plan the milestones", "plan this ticket", "what do we build first", or asks to split, add or change a milestone. Use it before any code. Writes the milestone lines into requirements.md and short steps into PLAN.md. No code and no tests come out of this skill. Adapted from obra/superpowers (MIT, © 2025 Jesse Vincent).
argument-hint: <nothing, or the change you want in the plan>
---

# Plan milestones

The creator said yes to the real issue. This skill cuts version 1 into milestones: as few as
the work needs, built one per session, each with a proof that it works.

A good plan lets a new session build a milestone three days later without guessing. Write down
what was decided: which files, which names, which values, which proof. Leave out what any
Python developer would do anyway.

## Rules for the whole skill

- Talk in plain, simple words. Ask ONE question per message, then wait.
- Only plan. No code and no tests in this session. Building starts in a new session.
  A hook holds this line: until the plan is approved, only notes (`.md` files) and `PLAN.md`
  can be written in the ticket folder.
- Plan version 1 only: what is inside the fence in `requirements.md`. "Later" is not planned.
- Never fill a gap with a guess. A gap is a question for the engineer or a senior colleague.
- The plan never changes what the creator agreed to. If it has to, the creator must say yes
  again: stop and go back to the `ticket-flow:clear-ticket` skill.
- Made-up names and data only in examples.
- **This plugin decides the steps in a ticket folder:** plan, review, tick, commit, close. The
  engineer's own rules, skills and agents for planning, reviewing, committing or closing work
  stay quiet here: do not run them on top of these steps. Their rules for HOW code is written
  (logging, code checks such as ruff, style) still count.
- **No branches in a ticket folder.** Every commit goes straight on the main line (the
  folder's one branch, `main` or `master`). Never make, switch, merge or delete a branch by
  yourself, even when the engineer's own rules say that work goes on a branch. A folder that
  is already on another branch: Step 0 says what to do.

## Step 0: is the ticket ready for a plan?

Read `requirements.md` and look at its Status line.

| What you find | Do this |
|---|---|
| `requirements.md` has a `## Closed` section | Check this first. The ticket is closed, and stays closed. Say so, and stop. No milestone is added to a closed ticket, and no plan is changed: a new wish is a new ticket with its own folder, and it starts there with `ticket-flow:clear-ticket`. |
| `**Status:** CONFIRMED BY CREATOR` | Go on. |
| `WAITING FOR CREATOR`, no Status line, or no file | Stop. Say that the plan waits for the creator's yes, and that the next step is the `ticket-flow:clear-ticket` skill. |

There is no way around this. If the engineer asks to plan on guesses, say no kindly and say
why: a plan built on a guess gets built twice.

Then look for milestone lines in `requirements.md`:

| What you find | Go to |
|---|---|
| No milestone lines | Step 1 |
| Milestone lines from before this skill: there is no `Plan approved by` line, and at least one milestone is ticked or the file has no `## The contract for version 1` section | The plan was made, and used, before this skill. Say the price, as in Step 7, and how many milestones are already ticked. Ask once: "Do you approve these milestones as the plan?" Yes: add the `Plan approved by` line (Step 7, item 1) right above the first milestone line, and change nothing else in the file. If the folder has `.git`, commit it by name, as in Step 7, item 3: `git add requirements.md`, the same `git status` check, then `git commit -m "Plan approved"`. Never push. Then say that building the first open milestone starts in a new session. No: it is a draft, the next row. |
| Milestone lines, but no `Plan approved by` line | The plan is a draft. Read it and `PLAN.md`, then go to Step 6. |
| Milestone lines and a `Plan approved by` line | The plan is done. Say so, and say that building the first open milestone starts in a new session. If the engineer wants to change the plan, see "Changing the plan later". |

**The branch.** Whichever row you took, unless it told you to stop: if the folder has `.git`,
run `git status` before anything else. Its first line names the branch. `main` or `master`: go
on. Anything else: do nothing by yourself. Tell the engineer which branch the folder is on
and what is on it that the main line does not have (`git log main..HEAD --oneline` lists
those commits; say `master` if that is the main line's name), and ask what to do. Do not go
on until that is settled. Then do what the engineer says: switching, merging or deleting a
branch is their call, never yours. Why: work that sits only on that branch must not be left
behind, or moved, without the engineer.

## Step 1: read before you plan

1. `requirements.md`: the real issue, the fence, the contract, what is Known, and
   `## Still open for the plan` if it is there.
2. What exists today. Read the scripts in the folder that the work will build on. The plan
   reuses what is there.
3. `MY_DEFAULTS.md`, if the project folder or the folder above it has one. It holds how this
   engineer's team builds things: how a script is laid out, where tests live, how things are
   run, what is read-only. Use a line from it where `requirements.md` is silent. No such
   file: carry on and do not mention it.
4. The ticket's `CLAUDE.md`. Its rules apply to the plan.

## Step 2: close what is still open

For each question under `## Still open for the plan`, ask the engineer if the answer has come.

| The answer | Do this |
|---|---|
| It came | Write it as **Known** with who said it, where and the date, the same way clear-ticket does. |
| Still open, and the plan does not depend on it | Leave it in the list. |
| Still open, and it decides how something is built | Do not guess. Either the plan waits for it, or an early milestone finds it out (see M1 in Step 4). The engineer picks. |
| It changes the fence or the contract | Stop. The creator agreed to something else. Back to `ticket-flow:clear-ticket`. |

## Step 3: the approach, in plain words

Before any milestone, write how version 1 will work as five to ten plain numbered steps. No
code. What it reads, what it does with it, what it writes, what happens when it goes wrong.

```text
1. Read today's export file from the shared folder.
2. Skip rows with no order number.
3. Keep the orders that are more than 3 days late.
4. Write them to a report file, one row per order.
5. If the export file is missing, write nothing and say so in the log.
```

If you used lines from `MY_DEFAULTS.md`, list them in the same message: "I'm planning with
these, as usual: 1. ... 2. ... Anything different for this ticket?"

Then ask one question: "Is this how you would do it?" Change it until the engineer agrees. A
wrong approach costs one message to fix here, and a whole milestone later.

## Step 4: cut it into milestones

Write the lines at the end of `requirements.md`, under a `## Milestones` heading. Change
nothing above that heading: the creator agreed to it.

Each line has exactly this form. Other tools read it, and the dashboard card shows
"M2 of 4" from it.

`- [ ] M1 — <what it delivers> · Done when: <proof>`

```markdown
## Milestones

- [ ] M1 — look at one real export file · Done when: user check — Sam opens one real file and its columns match the contract
- [ ] M2 — build the late orders report · Done when: test_reads_export, test_skips_rows_without_order_number, test_finds_late_orders, test_no_late_orders, test_writes_report, test_missing_export_writes_nothing pass
- [ ] M3 — run it on today's real export · Done when: user check — Sam runs the script on today's export and looks up three of its orders by hand
```

Rules for the lines:

- **One session each, and each one earns its place.** A milestone costs a whole session, and
  one with code costs a review as well. Only four things earn a milestone of their own:
  1. one real sample (the M1 rule below)
  2. a dry run, for risky work ("Risky work" below)
  3. a check only the engineer can do, when it cannot be done in the build session: it
     needs a real run at work, another day, or another person
  4. code that truly does not fit one session. Split it into as few parts as fit: M2a, M2b.

  Everything else is ONE build milestone, with all its tests. Cutting by function earns
  nothing: "read the export", "find the late orders" and "write the report" are three
  functions of one short script, not three milestones. A `user check` the engineer can do
  right there in the build session rides on the build milestone too: its "Done when" names
  the tests and the user check. So a short script is one build milestone, plus the checks
  that earn a milestone of their own.
- **A proof each.** Named tests that pass, for code. Or `user check — <what the engineer looks
  at>`, for something only a person can confirm. Both together is fine. A user check line
  says what the engineer looks at and what it is held against, never the answer itself (not
  "the report has 12 rows"): in the build session the engineer says what they see first.
- **No `<angle brackets>` in a real line.** A line with `<...>` is read as template text and
  skipped.
- **M1 is one real sample**, when the work reads anything the engineer did not make (a file
  from another team, a database, a web service). M1 checks that the login or the access works
  and looks at ONE real record. It only reads. Its proof is a user check. Why first: the rest
  of the plan rests on what we believe the data looks like, and one real sample beats belief.
  If the work reads nothing from outside, skip it and say so.
- **The riskiest part early.** Put the piece most likely to prove the plan wrong near the start.
- **Each one builds on the one before.** No milestone needs code from a later one.
- **The whole contract is covered.** Every Then and every And in the contract belongs to a
  milestone.

**Risky work.** If `requirements.md` starts with `RISKY:`, the plan needs three more things:

1. A dry-run milestone before any milestone that changes something. It lists what it would do
   and changes nothing. Its proof includes a user check of that list.
2. For the milestone that makes real changes: the steps to undo them, written in `PLAN.md`.
3. The name of the person who approved the change, from `requirements.md`. No name yet: that
   is an open question, and the plan waits for it.

## Step 5: the steps, in PLAN.md

Write `PLAN.md` in the project folder. One section per milestone. Keep it short: about one
line for each test or function.

```markdown
### M2 — build the late orders report

Files: `late_orders.py`, `tests/test_late_orders.py`

1. Test `test_reads_export`: a sample file with 3 rows gives 3 dicts with keys order, due, shipped.
2. Run the tests: it fails, the function is missing.
3. Write `read_export(path) -> list[dict]`.
4. Run the tests: all pass.
5. Test `test_skips_rows_without_order_number`: a row with an empty order column is left out.
6. Test `test_finds_late_orders`, then `late_orders(rows, today) -> list[dict]`: of three open
   orders due 1, 3 and 4 days ago, only the last one comes back.
7. Test `test_no_late_orders`: no order is late, the list is empty.
8. Test `test_writes_report`, then `write_report(rows, path)`: 2 late orders give a file with 2 rows.
9. Test `test_missing_export_writes_nothing`: no export file, so no report file and one line in the log.
```

A step names one of these: a test and what it checks, with exact values from
`requirements.md`; a function with its name, inputs, output and file; or a command and the
output that means it passed.

A step that decides nothing ("handle edge cases", "add tests", "TBD") is a gap. Fix it, or
turn it into a question.

Do not write the code here. If `PLAN.md` is longer than the code it describes, you wrote the
code: cut it back to names and tests.

## Step 6: check your own plan

Go through these yourself and fix what you find before you show the plan.

1. **Coverage.** Every Then and And in the contract has a milestone. Name any gap.
2. **Size.** Every milestone earns its place by one of the four reasons in Step 4. One that
   does not goes into the build milestone. Unsure if the code fits one session: keep it as
   one. The build session looks at the size again before it starts, and can still split it.
3. **Names.** A function has the same name, inputs and output in every milestone that uses it.
4. **Inputs that break things.** Think of the three to five inputs most likely to break it for
   a real user (an empty cell, a missing file, a strange ID). Each has a test, in the
   milestone that owns that code.
5. **The fence.** Nothing in the plan is from "Later" or "Not included".

## Step 7: the engineer approves

Show the milestone lines in chat and say that the steps are in `PLAN.md`. Then say the price,
in one line, before you ask for the yes:

`<N> milestones = <N> sessions, <R> reviews`

Every milestone is one session. Every milestone with code gets an independent review, and a
check-only milestone gets none. For the example in Step 4: "3 milestones = 3 sessions, 1 review".

Then ask: "Do you approve this plan?" If they want changes, make them, and show the lines and
the price again.

On their yes, in this order:

1. In `requirements.md`, add one line right under the `## Milestones` heading:
   `Plan approved by <engineer> (YYYY-MM-DD)`
2. In `tracking_log.md`: put the first milestone under `## Now working on` and the second
   under `## Next up`, each as its ID and short name. Add under `## Last update`:
   `YYYY-MM-DD — plan approved, <N> milestones`.
3. If the folder has `.git`:
   - Add the files you wrote, by name: `git add requirements.md PLAN.md tracking_log.md`.
   - Run `git status`. If it shows `ticket.md`, `.gitignore` or `CLAUDE.md` as new or
     changed, add them by name too. The first skill made them and nothing has committed them
     yet. Left out, the first build session would stop on them as leftover changes.
   - `git commit -m "Plan — <N> milestones"`. Never push.

   Never add everything at once: a data file or a file with logins could be lying in the
   folder. No `.git`: skip this step.
4. Tell the engineer: the plan is done, and building M1 starts in a new session. Then stop. Do
   not start building here.

## Changing the plan later

Plans meet reality. When a build session shows that the plan is wrong:

| What happened | Do this |
|---|---|
| A milestone truly does not fit one session | Split it: M3 becomes M3a and M3b. |
| A step in `PLAN.md` was wrong | Fix the step. |
| A milestone is missing | Add it with the next free number. |
| The job turned out risky: it would change a live system, and `requirements.md` has no `RISKY:` line | Say so. The engineer decides if the job goes on as risky work, never you. If it does: put `RISKY: <what it changes>` at the top of `requirements.md` (the one line a plan change adds above `## Milestones`), and add what "Risky work" in Step 4 asks for. The dry run comes before any change. |
| The creator wants something new | That is not a plan change. It goes to `ticket-flow:clear-ticket`: the creator confirms the new contract, or it waits under "Later". |

Never renumber or reword a ticked milestone. Show the engineer the changed lines and the new
price (as in Step 7), get their yes, put today's date on the `Plan approved by` line, and add
a line under `## Last update` in `tracking_log.md` that says what changed and why.

Then commit the change, if the folder has `.git`, so the next session does not find it as
leftover changes. In the middle of building a milestone: the changed files go in with that
milestone's commit. At any other time: add the files you changed, by name
(`git add requirements.md PLAN.md tracking_log.md`), then `git commit -m "Plan changed"`.
Never push.

## Common mistakes

| Mistake | Do this instead |
|---|---|
| Planning before the creator's yes | Stop and point to clear-ticket |
| Writing code or tests "to get ahead" | Only the plan. Building is a new session. |
| A milestone for each function of a short script | ONE build milestone. A milestone must earn its place. |
| Splitting a milestone "to be safe" | Only when the code truly does not fit one session |
| Asking for the yes without the price | Milestones, sessions and reviews in one line, then the question |
| "Done when: it works" | Named tests, or a user check that says what to look at |
| A user check line that gives the answer ("the report has 12 rows") | Say what the engineer looks at. They say what they see. |
| Skipping the real sample because the data "is surely like the ticket says" | M1 looks at one real record |
| A step like "handle errors" | Say which error and which test |
| Planning something from "Later" because it is easy | Version 1 only |
| Guessing the answer to an open senior question | It waits, or an early milestone finds it out |
| Rewording what is above `## Milestones` | The creator agreed to it. Leave it. |
| Asking about team defaults one by one | One message that lists them all |
