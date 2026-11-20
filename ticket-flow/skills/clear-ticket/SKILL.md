---
name: clear-ticket
description: Turns a vague ticket into a clear problem that the ticket creator has confirmed. Use at the start of any ticket or new project, whenever the user pastes a ticket, says a ticket is unclear, or asks "what does this ticket want", and whenever the user pastes or reports a reply from the ticket creator or a senior colleague. Use it before any plan, milestone or code. Sets up the ticket folder and writes requirements.md. No plan and no code come out of this skill.
argument-hint: <ticket text, or the creator's reply>
---

# Clear ticket

Tickets are usually vague. A plan built on a guess gets built twice. This skill gets from
"I am not sure what this ticket wants" to "the creator read the real issue and said yes".

The engineer does not need to understand the ticket to start. Their gaps are useful: every gap
goes to the person who can close it.

## Rules for the whole skill

- Talk in plain, simple words. No jargon. If a technical word is needed, explain it once.
- Ask ONE question per message, then wait. A wall of questions gets skimmed, and skimmed answers
  are guesses.
- No plan, no milestones, no code, no pseudo-code here. Those come after the creator's yes, in
  the next skill. Planning early hides the open questions behind work that looks like progress.
  A hook holds this line: until the yes, only notes (`.md` files) can be written in the ticket
  folder.
- Never fill a gap yourself. If nobody in the chat knows, it is a question for someone.
- Never answer for the engineer. Their own answer, even "I don't know", is what you need.
- Made-up names and data only in examples.
- **This plugin decides the steps in a ticket folder:** plan, review, tick, commit, close. The
  engineer's own rules, skills and agents for planning, reviewing, committing or closing work
  stay quiet here: do not run them on top of these steps. Their rules for HOW code is written
  (logging, code checks such as ruff, style) still count.

## The three labels

Every fact about the ticket carries one label. Use the same three words everywhere.

| Label | Meaning |
|---|---|
| **Known** | Written in the ticket or the code, or said by the creator or a senior. Carries its source and date. |
| **Guess** | Someone thinks so, but nobody confirmed it. |
| **Unknown** | Nobody here knows. |

A Guess is as open as an Unknown. Neither is settled until someone who knows has seen it: as
a real question, or on a list of things we assume out loud (Step 4).

## Step 0: where are we?

This skill usually runs over several sessions, because the creator takes time to answer. So
first read `requirements.md` in the project folder, if there is one, and pick up from its
Status line:

| What you find | Go to |
|---|---|
| `requirements.md` has a `## Closed` section | Check this first. The ticket is closed, and stays closed. Say so, and stop. A new wish is a new ticket with its own folder: the engineer makes it (the dashboard's **+ New project** does it), and this skill starts there. |
| No `requirements.md`, or it holds only empty template text | Step 1 |
| `**Status:** WAITING FOR CREATOR` | Step 6 (ask for the creator's reply) |
| `**Status:** CONFIRMED BY CREATOR` | This skill is done. Say so, and say the next step is planning the milestones, in a new session (or `/clear`). |
| Real content but no Status line (a ticket started before this skill) | Ask once: "Did the creator already confirm what this ticket is about?" Yes: add the CONFIRMED Status line and the proof (Step 8), and change nothing else in the file. No: go to Step 1. What the file says counts as the engineer's notes: keep it, and add the new sections around it. |

Then check the starter files. Every ticket folder needs these three. The dashboard card is
filled from `tracking_log.md`, so without it the card stays empty.

| File | If it is missing |
|---|---|
| `CLAUDE.md` | Write it from "Starter files" at the end of this skill |
| `tracking_log.md` | Same |
| `.gitignore` | Same |

Never overwrite one that is already there. One line to the engineer is enough: "I set up the
folder."

## Step 1: read before you ask

1. The ticket. If the user pasted it and there is no `ticket.md`, save it as `ticket.md` in
   the layout below. Keep the `##` heading exactly as it is, wherever the ticket came from:
   the dashboard card takes its Goal from the text under it. Leave `Created by:` empty if the
   ticket does not name its creator.

   ```markdown
   # <TICKET-KEY>

   Created by: <name>

   ## Description (pasted from Jira)
   <the pasted text, unchanged>
   ```

   No ticket key in the text: ask for it, never invent one. A `ticket.md` that is already
   there is never rewritten.
   If this is the engineer's own idea and there is no ticket, see "No ticket" at the end.
2. What exists today. Look for scripts or notes in the folder that already do part of the job.
   If there are any, tell the engineer in a few plain sentences what they do now. People often
   ask for something that half exists.
3. `MY_DEFAULTS.md`, if the project folder or the folder above it has one. It holds what is
   usually true for this engineer's team. Use a line from it only where the ticket is silent,
   and label it **Guess (team default)**. Step 4 checks all of them with the engineer in one
   message. No such file, or it cannot be read: carry on and do not mention it. The file is
   optional.

Then say you have read it, and that four questions come first, one at a time, and that
"I don't know" is a good answer.

## Step 2: the engineer goes first

Ask these four, in this order, one per message. Do not give your own view yet, and do not hint.
Give each answer a label.

1. **The pain.** Who is hurting, and what do they do by hand today?
2. **The fog words.** Which words in the ticket could mean two things?
3. **The stakes.** What happens if nobody does this for two weeks?
4. **The smallest first version.** What is the least we can build that proves the idea?

Why the engineer goes first: they own the ticket. If you answer first they will agree with
you, and what they did not know stays hidden. What they cannot answer is exactly what the
creator must be asked.

## Step 3: add what was missed

Now give your own reading, next to theirs. Go through the three checks below. The goals are
fixed. The questions are yours to write so they fit this ticket. If a check does not fit, skip
it and say which one and why, in one line.

**Check 1, clear the fog.** Goal: no word in the ticket can mean two things.
Things that are often foggy: what starts the job and when; where the true data lives; how one
record is matched to another; what is in and what is out; what comes out at the end and who
gets it.

**Check 2, set the fence.** Goal: everyone agrees what the work touches and what it leaves alone.
Does it only read, or does it change things? Does it run once, on a schedule, or when someone
starts it? Does it cover old records too, or only new ones from now on?

**Check 3, try to break it.** Goal: know what should happen when things go wrong.
What if it runs twice? What if there are far more records than expected? What if the source is
down? What if the data is wrong or half empty?

**Risky work.** If the job would change, delete, close or send anything in a live system, say
so plainly, and put `RISKY: <what it changes>` at the top of `requirements.md`. The first
version is then a dry run: it lists what it would do and changes nothing. Add two questions:
how do we undo a change, and who must approve it. This rule is only for risky work. A job that
only reads does not need a dry run.

Give each new point a label, the same way as the engineer's answers.

## Step 4: every Guess and Unknown goes to someone who knows

Sort them by who can answer:

- **The creator**: what they want, why, what counts as done, what is in and out.
- **A senior colleague**: how things work here. Where it runs, which login, who gets told when
  it fails.
- **The engineer**: what they can decide or look up themselves.

For the creator and the senior colleague there are two kinds. People answer three questions
and skim fifteen, so ask only what must be asked:

- **A real question**: a wrong guess here does harm or changes what is built. Wrong data
  changed, sent or deleted, the wrong person told, a different script built. Anything a risky
  job would change is always a real question.
- **An assumption**: a wrong guess is cheap to put right later (a column name, a file name,
  the wording of a mail). These go in one list under the line
  "I will assume these unless you say no:".

An Unknown with no sensible guess has nothing to assume: it is a real question.

Team defaults come first, if you used any. Show them all in ONE message, not one by one:
"I'm assuming these, as usual: 1. ... 2. ... Anything different for this ticket?" The ones the
engineer leaves alone become **Known** `(team default, <date>)`. One that is different for
this ticket becomes a normal question.

Then ask the engineer's questions, one at a time, each with your suggested answer and a
one-line reason.

Write the creator's message, ready to paste:

- the real questions first: numbered, the most blocking first
- plain words, and each one answerable in one line
- a Guess is asked as a check: "Is it right that ...?"
- then the assumptions, under "I will assume these unless you say no:", with letters
  (a, b, c), so the creator can answer "b is wrong"
- more than about seven real questions: suggest a 15-minute call instead and give the list as the agenda

Do the same, shorter, for the senior colleague.

Check before you go on: every Guess and every Unknown is a real question or on an assume list.
Nothing is left out because it seemed small.

## Step 5: write it down, then wait

Write `requirements.md` in the project folder with this layout. Keep the Status line exactly
in this form: other tools read it.

```markdown
# <TICKET-KEY> — requirements

**Status:** WAITING FOR CREATOR (since YYYY-MM-DD)

## What the ticket says
<the ticket in one or two plain sentences>

## What exists today
<what is already there, or "Nothing yet">

## What we know
- [Known] <fact> (<source>, <date>)
- [Guess] <fact>
- [Unknown] <what nobody knows>

## Questions for the creator (<name>)
1. <question>

## Questions for a senior colleague
1. <question>

## Assumed unless someone says no
- <what we assume> (for <name>)

## Answers so far
<empty until a reply is pasted>
```

In `tracking_log.md`, set `## Now working on` to one line that starts like this, so the
dashboard card shows the ticket as waiting, and for what:

`PENDING (creator, YYYY-MM-DD): waiting for <name> to answer <N> questions.`

<N> counts the real questions only: an assumption needs no answer.
Keep that line true as things move, so the card always says where the ticket stands:
`... to answer <N> more questions.` after a partial reply, and `... to confirm the real issue.`
in Step 7.

Show the two messages in chat, ready to copy. Then stop. Tell the engineer to send them and to
come back with the reply. No other work on this ticket happens while it waits.

## Step 6: the creator replies

Ask the engineer what the creator answered. How they bring it is their call:

- **A long or complex answer:** paste it as it is. That is quicker than retelling it, and
  nothing gets lost.
- **A short or simple answer:** they can say it in their own words.

Never insist on a paste, and never ask for a written recap of a call.

With the answer:

1. Match each answer to its question. Replies are often rough ("2: close, never delete").
2. Change the label to **Known** and add who said it, how it reached you, and the date. Only
   two labels say how: `(Maria, pasted from Slack, 2026-11-15)` for pasted words,
   `(Maria, told by Sam, 2026-11-15)` when the engineer retold it. Copy the answer into
   "Answers so far". Use quote marks only for pasted words.
3. An assumption they left alone in their reply becomes
   `[Known] <fact> (assumed, <name> did not object, <date>)`. One they correct is an answer
   like any other. No reply yet means nothing was left alone: it stays a Guess.
4. Look for anything new: a new rule, a new wish, a "you missed X". New things open new
   questions. Add them and go back to Step 4.
5. An answer you cannot read clearly stays open. Ask again, do not guess what they meant.

Replies from a senior colleague are handled the same way.

Repeat until no creator question is open. Senior questions still open at that point do not
block the creator: list them under `## Still open for the plan`. The plan deals with them
first.

## Step 7: say the real issue back

When nothing for the creator is open, write three things and add them to `requirements.md`:

```markdown
## The real issue
<two to four plain sentences: who has the problem, what it costs them today, what they want instead>

## The fence
- **Version 1:** <the smallest first version>
- **Later:** <what waits>
- **Not included:** <what this work never touches>

## The contract for version 1
- **Given** <the starting situation>
- **When** <what happens or runs>
- **Then** <what must be true afterwards, something a person or a test can check>
- **And** <what happens when it goes wrong>
```

Use more than one Given / When / Then block if version 1 does more than one thing.
Whatever was assumed and shapes version 1 must show in these three parts, in plain words: the
creator's yes then covers it too.

Give the engineer a message to paste that holds these three parts and ends with:
"Is this right? Reply yes, or tell me what is wrong." The Status stays WAITING FOR CREATOR,
and the PENDING line in `tracking_log.md` now says `waiting for <name> to confirm the real issue.`

## Step 8: is it a real yes?

The engineer brings the creator's reply, pasted or in their own words (their call, as in
Step 6). Read it strictly.

If it was not pasted, ask one short question before you accept a yes: "Did they add any 'but'
or any extra wish?" A retold yes often drops the "but". Then wait. The file can say there was
no "but" only when you asked and the engineer answered. The engineer's own idea (see
"No ticket"): skip this question. Nobody retold the yes: they say it themselves, in this chat.

| The creator says | What it is | What to do |
|---|---|---|
| "Yes", "Approved", "Correct, go ahead" | A real yes | Save it (below). |
| "Looks good, but can it also ..." | Not a yes. It asks for something new. | Two ways out: add it to the contract and send it again, or the creator agrees in writing that it waits for a later version. The creator picks, not the engineer: write a short message that asks them which. |
| "You missed X" / "No, it's about Y" | Not a yes | Back to Step 4 with the new facts. |
| A thumbs-up from someone else, or "I think she's fine with it" | Not the creator's answer. Nobody has it yet. | Ask the engineer to get the creator's own answer. |
| Nothing yet | Still waiting | Stay in WAITING. |

There is no way around this step. If the engineer asks to go ahead on guesses or to skip the
confirmation, say no kindly and say why: the yes is the only proof that the work solves the
creator's problem, and one message costs less than building the wrong thing. Then help with
what does move things: a shorter message, a call, or a reminder to the creator.

If the creator is gone or cannot be reached for long, ask the engineer who owns the ticket
now. That person takes the creator's place, and their name goes in the file.

On a real yes:

1. In `requirements.md`, change the Status line and add the proof:

   ```markdown
   **Status:** CONFIRMED BY CREATOR (YYYY-MM-DD)

   ## The creator's yes
   Pasted:
   > <their exact words>
   (<name>, <where: Slack, Jira comment, email, call>, <date>)
   ```

   No paste: in place of the first two lines write `Told by <engineer>: <what the creator said>`.
   `Pasted:` and `Told by <engineer>:` are the only two labels for a reply the engineer
   brings (their own idea: see "No ticket"), and the proof says only what really happened.
   Never write that something was checked or ruled out ("confirmed, no but") unless you asked
   it in this chat and the engineer answered. Then add their answer as a line of its own:
   `Asked about a "but": <the engineer's answer>`.

2. In `tracking_log.md`: remove the PENDING line, write
   `Plan the milestones` under `## Now working on`, and add under `## Last update`:
   `YYYY-MM-DD — real issue confirmed by <name>`.
3. Tell the engineer: this part is done, and planning the milestones starts in a new session (or `/clear`).
   Then stop. Do not start the plan here.

## No ticket (the engineer's own idea)

The engineer is the creator. Run the same steps: they still answer the four questions, and the
three checks still apply. In Step 8 they confirm the real issue themselves, in this chat.
Nobody pasted or retold a reply, so neither `Pasted:` nor `Told by <engineer>:` is true here.
In place of those lines write `Said in this chat: <the engineer's own words>`, and under it
`(own project, <name>, <date>)`.

## Starter files

Step 0 writes these when they are missing. Put the real ticket key and today's date in place
of the `<...>` parts. Keep the three `##` headings of `tracking_log.md` exactly as they are:
the dashboard reads them.

`CLAUDE.md`:

```markdown
# <TICKET-KEY>

- What was agreed with the creator: `requirements.md`
- Where the work stands: `tracking_log.md` (the dashboard card is filled from it)
```

`tracking_log.md`:

```markdown
# <TICKET-KEY> — tracking log

## Now working on
Understand the ticket

## Next up
Get the creator's yes on the real issue

## Last update
YYYY-MM-DD — folder set up, ticket read
```

`.gitignore`:

```text
# Keep data and noise out of every diff and review.

# Python caches
__pycache__/
.pytest_cache/
*.pyc

# Claude Code's own files (session notepads, local settings)
.claude/

# Logins
.env

# Data and exports: may hold real data
*.csv
*.xlsx
*.xls

# Noise
*.log
*.zip
*.bak
```

## Common mistakes

| Mistake | Do this instead |
|---|---|
| Asking all four questions in one message | One per message |
| Answering a question for the engineer "to save time" | Wait for their answer. "I don't know" is fine. |
| Treating a Guess as settled because it sounds right | It goes to someone who knows: a real question, or the assume list |
| Sending the creator a long list of small questions | Real questions only where a wrong guess does harm or changes what is built. The rest: one assume list. |
| Asking the creator about servers, logins or how to undo a change | Those go to a senior colleague |
| Running every check when one does not fit | Skip it and say which and why |
| Writing a plan, milestones or pseudo-code "while we wait" | Nothing until the creator's yes |
| Taking "looks good, but ..." as a yes | It is a new ask. Settle it first. |
| Insisting on a paste, or on a written recap of a call | Paste or tell is the engineer's call |
| Writing a retold answer as if it were a quote | Say which it was: `Pasted:`, or `Told by <engineer>:` |
| Writing "confirmed, no but" when nobody asked | Only what happened. A check goes in the file only if you asked it and the engineer answered. |
| Asking about team defaults one by one | One message that lists them all |
