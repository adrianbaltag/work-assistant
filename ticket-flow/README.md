# ticket-flow (Claude Code plugin)

From a vague ticket to a clear, confirmed problem, then milestones built one per session.
One plugin holds the skills, the code reviewer and the hooks, so there is one thing to install.

It belongs to the Work Assistant app and needs its folder: the hook code (`work_jira_hooks.py`)
and `settings.ini` live there, not in the plugin.

| Part | What it does |
|---|---|
| `clear-ticket` (skill) | From a vague ticket to a real issue the creator said yes to. |
| `plan-milestones` (skill) | Cuts the confirmed ticket into milestones, each with a proof. |
| `build-milestone` (skill) | Builds one milestone per session: test, code, proof, review, tick. |
| `code-reviewer` (agent) | Strict and read-only. Reviews each code milestone before it is ticked. |
| the hooks | Dashboard sync, the next step at session start, the gate, the end-of-milestone checklist. |

## The flow

1. **clear-ticket.** You answer four questions (the pain, the fog words, the stakes, the smallest
   first version). "I don't know" is fine: every guess and unknown becomes a question for the
   ticket's creator. No plan until the creator says a clear yes.
2. **plan-milestones.** The confirmed ticket is cut into milestones. You approve the plan.
3. **build-milestone.** One milestone per session: test first, code, proof, an independent strict
   review, the tick. Then a new session for the next one. After the last one, the creator's yes
   closes the ticket.

## The gate

Inside a ticket folder (a folder under `work_jira_folder=` from `settings.ini`), a hook checks every
file Claude is about to write:

| Where the ticket stands | Claude can write |
|---|---|
| The creator has not said yes | notes only |
| The creator said yes, no approved plan yet | notes and `PLAN.md` |
| Approved plan with an open milestone | everything |
| A milestone was ticked in this session | notes only, until a new session |
| Every milestone is ticked | notes and `PLAN.md` (new code needs a new milestone first) |
| The ticket is closed | notes only (a new wish is a new ticket, with its own folder) |

A note is any `.md` file except `PLAN.md`, and `.gitignore`. A closed ticket stays closed: a new
wish is a new ticket with its own folder. Limits, and what to do when a write is stopped:
the app's README.md, "The gate: no code before the yes".

## Install (Windows PowerShell)

The full steps are in the app's README.md, "Sync with work_jira", "Set it up (once)". In short:

```powershell
cd $HOME\Desktop\work-assistant
claude plugin marketplace add ./
claude plugin install ticket-flow@work-assistant
.venv\Scripts\python check_setup.py
```

The last line checks the install and saves where the app folder is (`ticket-flow-home.txt` in Claude
Code's own folder), so the hooks can find it. Start Claude again afterwards.

The hooks start with the plain command `python`, so `python --version` must work in a new window.

## Update and remove

After a `git pull` in the app folder:

```powershell
claude plugin update ticket-flow@work-assistant
```

To take it out:

```powershell
claude plugin uninstall ticket-flow@work-assistant
claude plugin marketplace remove work-assistant
```

## How the hooks find the app folder

Each hook runs `scripts/run_hook.py` with one word (`gate`, `stop`, ...). That script looks for the
app folder in two places:

1. Around the plugin folder. This is the case when Claude Code reads the plugin in place.
2. In `ticket-flow-home.txt`, written by `check_setup.py`. This is the case when Claude Code copied
   the plugin to its own cache.

Then it runs `work_jira_hooks.py` there with the app's own Python (`.venv`). If it finds nothing,
you see one line when Claude starts, and the hooks do nothing: they never stop Claude by mistake.

## Credit

The skills are adapted from [obra/superpowers](https://github.com/obra/superpowers), MIT license
(`LICENSE-superpowers.txt`).
