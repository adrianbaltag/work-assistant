# Work Assistant

A small web page that runs on your own laptop and shows your work projects in one place:

- **Dashboard** of every project, critical ones first, with tabs for Critical, Pending and Gone quiet.
- **Project cards** where you edit the notes, fields and files of a project (nothing is ever deleted: it goes to the Archive).
- **Ask Claude** about one project, or about all of them ("What should I work on this morning?").
  Claude can *suggest* changes; nothing is saved until you click Approve.
- **Slack button** (optional) that glows when you have unread mentions or direct messages.

Everything stays on your laptop. The page is only reachable from your own computer (http://127.0.0.1:5050).

The commands below are for **Windows PowerShell** (the work laptop). A short Mac section is at the end.

---

## How it works

### One folder per project

The app doesn't have a database. Your projects are ordinary folders and text files on your laptop,
all inside **one projects folder** (you choose where, in `settings.ini`). For example:

```
Desktop\projects\                  <- the projects folder (projects_folder= in settings.ini)
├── NET5G-42\                      <- one project. The folder name is the project's ID.
│   ├── note.md                    <- the project's note: fields + your notes + history
│   ├── sessions\                  <- dated work summaries, e.g. 2026-10-21.md
│   └── raw\                       <- source material: emails, transcripts, screenshots, logs
├── NET5G-57\
├── my_idea\                       <- IDs don't have to be Jira tickets
└── _archive\                      <- archived projects (made by the app)
```

A folder counts as a project when it has a `note.md` inside. You can open and edit all of these
files with any editor (Notepad, VS Code, Claude Code) as well as in the app. The app re-reads them
every time you open the page or a card, so it always shows what's on disk.

### What's in note.md

The top of the file is a block of **fields** between two `---` lines. Below it are your own notes,
and at the bottom a **History** list, newest first:

```
---
title: Fix the RAN alarms
status: active
priority: critical
next: ask the vendor for the new firmware
blocked_by: waiting on lab access
jira: NET5G-42
folder: C:\work_jira\NET5G-42
tags: alarms, ran
---

## Goal
Stop the false alarms on the north sites.

## History
- 2026-10-21 · you · vendor says firmware ships Friday
- 2026-10-18 · you · started
```

| Field | What it means |
|---|---|
| `title` | The project's name on the dashboard. |
| `status` | `active` (working on it), `pending` (waiting on something) or `idea` (not started). Finished = Archive it. |
| `priority` | `critical`, `high` or `normal`. **Only you set it**: Claude never changes it. |
| `next` | Your next step. |
| `blocked_by` | What you're waiting for, if anything. |
| `jira` | The Jira ticket ID, like `NET5G-42`. Used by the **Open in Jira** button. |
| `folder` | Where the project's code or scripts live, for example your `work_jira` folder. Information only: the app never opens or changes it. |
| `tags` | Any words that help you find it. |

### How it fits with Jira

The app doesn't connect to Jira or copy anything from it. The link is only the ticket ID:

- When you make a project with **+ New project** and give it an ID that looks like a Jira ticket
  (`NET5G-42`), the app names the folder `NET5G-42` and fills the `jira:` field for you.
  An ID like `my_idea` or `phase-2` is fine too; its `jira:` field just starts empty.
- On each card, **Open in Jira** opens that ticket in your browser, using `jira_url=` from
  `settings.ini` (see Part 1, Step 3).
- Your code stays where it is (for example in `work_jira`). Write its path in the `folder:` field
  so you can find it from the card.
- If you set `work_jira_folder=`, cards can follow your work folders by themselves.
  See [Sync with work_jira](#sync-with-work_jira-optional).

### The dashboard

- **Tabs:** All open · Critical · Pending · Gone quiet. "Gone quiet" = nothing in the project's
  folder changed for 7 days or more (ideas never go quiet).
- **Order:** critical projects first, then the ones untouched the longest.
- **Click a project** to open its card. There you can edit the fields, the full note.md,
  the files in `sessions\` and `raw\` (new, edit, rename, upload, paste), add a History line,
  open the notes folder, open the Jira ticket, and **Ask Claude** about this project.
- **Nothing is ever deleted.** Deleting a file or a project moves it to an archive folder;
  the **Archive** page puts it back with **Restore**.
- If a file changed on disk while you were editing it in the app (for example Claude Code saved it),
  the app warns you instead of overwriting it.

### Ask Claude

Claude reads the project's files (note.md, sessions, raw) and answers your question. In a project card
it can also **suggest** changes (fields, a History line, a session note). You see them first;
nothing is saved until you click **Approve**. The **Ask Claude** page asks about all your open
projects at once (answers only, no changes).

---

## Part 1: Install (once)

### What you need

- **Python 3.10 or newer.** Check by typing `python --version` in PowerShell.
- **Git.** Check with `git --version`.
- The **VPN** on, if you are not in the office.

### Step 1: Download the app

Open **PowerShell** (Start menu, type "PowerShell") and run these two lines:

```powershell
cd $HOME\Desktop
git clone https://github.com/adrianbaltag/work-assistant.git
```

You now have a folder `work-assistant` on your Desktop.

### Step 2: Make the app's own Python box and install its packages

```powershell
cd $HOME\Desktop\work-assistant
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

- The first line moves into the app folder.
- The second line makes `.venv`, a private copy of Python just for this app, so the packages
  below don't mix with anything else on your laptop.
- The third line installs the packages the app needs (Flask, the Claude library and the Slack library).

If `python` is not found, try `py` instead of `python` in the second line.

> Why `.venv\Scripts\python` and not "activate the venv"? Activating needs a PowerShell
> permission that is often switched off on work laptops. Calling the venv's Python directly
> always works.

### Step 3: Make your settings file

```powershell
copy settings.ini.example settings.ini
notepad settings.ini
```

Notepad opens. Each line explains itself. The two you must change:

- `projects_folder=`: the folder that holds your projects, one sub-folder per project.
  For example `C:\Users\YOUR-NAME\Desktop\projects`. Make the folder if it doesn't exist yet;
  the app's **+ New project** button fills it.
- `jira_url=`: the start of your Jira address, the part before `/browse/`.
  To find it, open any ticket in Jira and look at the browser's address bar, for example
  `https://jira.yourcompany.com/browse/ABC-123`. Copy only the part before `/browse/`:

  ```
  jira_url=https://jira.yourcompany.com
  ```

  The app uses it for the **Open in Jira** button on each project card: it adds `/browse/` and the
  ticket ID from the card's **Jira** field. So a card whose Jira field says `ABC-123` opens
  `https://jira.yourcompany.com/browse/ABC-123`. Leave `jira_url=` empty and the button stays off.

Optional: `work_jira_folder=` is the folder that holds your work project folders, for example
`C:\Users\YOUR-NAME\Desktop\work_jira`. Leave it empty if you don't use one. See
[Sync with work_jira](#sync-with-work_jira-optional).

Save and close Notepad. `settings.ini` is yours alone: it is never uploaded anywhere.

### Step 4: Claude login

The app talks to Claude with the same login your Claude Code uses at work: two environment variables,
`ANTHROPIC_AUTH_TOKEN` (your token) and `ANTHROPIC_BASE_URL` (the company gateway address).

They may already be set on your laptop. Check in a **new** PowerShell window:

```powershell
echo $env:ANTHROPIC_BASE_URL
```

- It prints an address: they are set. Nothing to do.
- It prints nothing: you'll type them in each time you start the app (Part 2).
  Ask your team lead for the gateway address and your token.

Ask Claude costs money per question (about $0.10 with the default settings). The `text_limit=`
line in `settings.ini` controls how much Claude reads per question.

### Step 5 (optional): Slack

Skip this whole step if you don't want the Slack button. The rest of the app works without it.

> ### ⚠️ Make your OWN Slack app. Never share one.
>
> Each person needs their own Slack app, made from their own Slack account.
> Do **not** reuse a colleague's app or tokens, and do not make one app "for the team".
>
> **Why:** the instant connection belongs to the *app*, not to the person. If several people
> run the same app, Slack hands each new message to *any one* of the connected laptops
> ([Slack's own words](https://docs.slack.dev/apis/events-api/using-socket-mode/): "each payload
> may be sent to any of the connections"). So your DMs could light up a colleague's button
> instead of yours, and theirs yours.
>
> **At work**, a Slack admin must approve each new app. Expect to send one approval request
> (for your own app) and wait for it.

**5a. Create the app (2 minutes)**

1. Go to https://api.slack.com/apps and sign in with your work Slack.
2. Click **Create New App**, then **From a manifest**.
3. Pick your work Slack workspace. Click **Next**.
4. Choose the **JSON** tab. Delete what's in the box. Open the file `slack-app-manifest.json`
   from the app folder in Notepad, copy everything, and paste it into the box.
5. In the pasted text, change `"name": "Work Assistant"` to include your name,
   like `"name": "Work Assistant - Alex"`, so the admin can tell whose app it is.
6. Click **Next**, then **Create**.

The manifest is a ready-made list of what the app may do, so you don't have to tick 11 permissions
by hand. It only *reads* your messages; it can't post, delete or change anything.

**5b. Install it and copy your user token (`xoxp-…`)**

1. In the left menu, click **Install App**, then **Install to Workspace** (or **Request to Install**
   at work, and wait for the admin's approval, then come back here).
2. Click **Allow**.
3. Copy the **User OAuth Token**. It starts with `xoxp-`. This is your `SLACK_USER_TOKEN`.

**5c. Make the instant-connection token (`xapp-…`)**

1. In the left menu, click **Basic Information**. Scroll to **App-Level Tokens**.
2. Click **Generate Token and Scopes**. Name it anything (for example `instant`).
3. Click **Add Scope** and pick `connections:write`. Click **Generate**.
4. Copy the token. It starts with `xapp-`. This is your `SLACK_APP_TOKEN`.

**Which token is which?**

| Token | Starts with | Where | What it does |
|---|---|---|---|
| `SLACK_USER_TOKEN` | `xoxp-` | OAuth & Permissions, "User OAuth Token" | Your login: reads *your* DMs and mentions |
| `SLACK_APP_TOKEN` | `xapp-` | Basic Information, "App-Level Tokens" | The doorbell: lets Slack tell the app about new messages at once |

**Keep both tokens in your password manager.** Never put them in a file in the app folder,
in `settings.ini`, in an email or in a Slack message. Anyone with your `xoxp-` token can read your Slack.

---

## Part 2: Start the app (every time)

Tokens typed into a PowerShell window live **only in that window**. When you close the window
(or restart the laptop) they are gone, so you set them again each time you start the app.
That's on purpose: nothing secret is saved on disk.

**1. Open PowerShell and go to the app folder:**

```powershell
cd $HOME\Desktop\work-assistant
```

**2. Set your tokens.** Run each line on its own. It asks a question; paste the token, press Enter.

Claude (skip these two if Step 4 showed they're already set):

```powershell
$env:ANTHROPIC_BASE_URL = Read-Host "Paste the Claude gateway address"
$env:ANTHROPIC_AUTH_TOKEN = Read-Host "Paste your Claude token"
```

Slack (skip if you don't use Slack):

```powershell
$env:SLACK_USER_TOKEN = Read-Host "Paste SLACK_USER_TOKEN (xoxp-...)"
$env:SLACK_APP_TOKEN = Read-Host "Paste SLACK_APP_TOKEN (xapp-...)"
```

> Why `Read-Host` and not `$env:SLACK_USER_TOKEN = "xoxp-..."`? PowerShell saves every command you
> type in a history file on disk. With `Read-Host`, the command has no token in it; the token is only
> your answer to the question, which isn't saved. (The token does show on screen while you paste,
> so don't do this while sharing your screen.)

**3. Check everything (recommended, takes about 10 seconds):**

```powershell
.venv\Scripts\python check_setup.py
```

Every line should say `[ OK ]` (or `[SKIP]` for Slack or `work_jira_folder=` if you don't use them). A `[FAIL]` line says what
to fix. Fix it and run the check again. It never prints your tokens, so it's safe to show a colleague.

**4. Start the app:**

```powershell
.venv\Scripts\python app.py
```

Open http://127.0.0.1:5050 in your browser. **Leave the PowerShell window open** while you use the
app. To stop the app, click the PowerShell window and press **Ctrl+C**.

---

## Sync with work_jira (optional)

For people who keep one folder per ticket in a `work_jira` folder and work on it with Claude Code.
With this set up, the dashboard follows that work by itself:

| When | What happens | Tokens? |
|---|---|---|
| You click **+ New project** with the box **Work project** ticked | The app makes the card and `work_jira\<ID>\`, with your Jira description and "Created by" in `ticket.md`. If that folder already exists, the app leaves it as it was and tells you for 5 seconds that the description was not saved. | none |
| You open a new project folder in VS Code and start Claude | A hook tells Claude to set the folder up from `work_jira\_templates`, read `ticket.md`, then run clear-requirements and grill-me. | Claude's normal work |
| The folder has a `tracking_log.md` but no card yet | After Claude's reply, a hook asks Claude to run one `project_note.py create` command. | a few |
| Claude updates `tracking_log.md` | After Claude's reply, a hook copies it to the card: *Next up* → `next:`, *Last update* → a History line, *Now working on* starting with `PENDING (who, date): reason` → status pending + `blocked_by:`. | none |
| You move a finished folder out of `work_jira` (for example to your prod folder) | The next time Claude Code starts, a hook moves the card to the Archive page. **Restore** brings it back. | none |

Only cards made this way (they have `source: work_jira`) are ever archived by the hook. Your other
cards and ideas are never touched. Nothing ever changes `priority`.

> **Open the project folder, not the whole `work_jira`.** In VS Code: File → Open Folder →
> `work_jira\ABC-123`. The hooks know the project from the folder you opened. If you open all of
> `work_jira`, the hooks only keep existing cards up to date and never ask Claude for anything.

### Set it up (once)

**1. Add the folder to `settings.ini`** (Part 1, Step 3), then run `.venv\Scripts\python check_setup.py`.
The `work_jira_folder:` line should say `[ OK ]`.

**2. Find your exact paths.** In PowerShell:

```powershell
"$HOME\Desktop\work-assistant".Replace('\', '/')
```

It prints something like `C:/Users/YOUR-NAME/Desktop/work-assistant`. Use that in step 3 wherever
you see `C:/Users/YOUR-NAME/Desktop/work-assistant`.

> Why forward slashes? Windows accepts them, and in JSON a backslash must be written twice (`\\`).
> Forward slashes avoid that mistake.

**3. Add the hooks to your Claude Code user settings.** Open the file in VS Code:

```powershell
code $HOME\.claude\settings.json
```

The file is one `{ ... }` block. Add the `"hooks"` and `"permissions"` parts below inside it, next to
what is already there (put a comma between parts). If the file is empty, paste all of this.
If you already have a `"permissions"` part with an `"allow"` list, add the two lines to that list instead.

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "timeout": 30,
          "command": "C:/Users/YOUR-NAME/Desktop/work-assistant/.venv/Scripts/python.exe",
          "args": ["C:/Users/YOUR-NAME/Desktop/work-assistant/work_jira_hooks.py", "stop"] } ] }
    ],
    "SessionStart": [
      { "hooks": [ { "type": "command", "timeout": 30,
          "command": "C:/Users/YOUR-NAME/Desktop/work-assistant/.venv/Scripts/python.exe",
          "args": ["C:/Users/YOUR-NAME/Desktop/work-assistant/work_jira_hooks.py", "session-start"] } ] }
    ]
  },
  "permissions": {
    "allow": [
      "PowerShell(C:/Users/YOUR-NAME/Desktop/work-assistant/.venv/Scripts/python.exe C:/Users/YOUR-NAME/Desktop/work-assistant/project_note.py *)",
      "Bash(C:/Users/YOUR-NAME/Desktop/work-assistant/.venv/Scripts/python.exe C:/Users/YOUR-NAME/Desktop/work-assistant/project_note.py *)"
    ]
  }
}
```

Save. VS Code underlines a JSON mistake in red: fix it before you go on.

What each part does:

- `"command"` + `"args"`: runs the app's own Python with `work_jira_hooks.py` directly, with no
  shell in between, so spaces and quotes can't break it. Why not one line like
  `"command": "python work_jira_hooks.py stop"`? That goes through a shell, and on Windows the
  shell may not be the one you expect.
- `Stop` runs after every Claude reply. `SessionStart` runs when a Claude session starts.
  Both finish in well under a second and send nothing over the network.
- The two `allow` lines let Claude run `project_note.py` without asking you each time. There is
  one for PowerShell and one for Git Bash, because Claude Code on Windows can use either.
  If Claude still asks, it typed the command a little differently: answer Yes.

**4. Move your old allow rules (if you have any).** If `work_jira\.claude\settings.local.json` has a
`"permissions"` → `"allow"` list, copy those lines into the `"allow"` list from step 3. When you open
one project folder, Claude Code no longer reads the settings inside `work_jira\.claude`.

**5. Add these lines to `work_jira\CLAUDE.md`:**

```markdown
## Dashboard sync
- Started inside a project folder (work_jira\<name>) = that is the project. Don't ask which one.
- Every project, Jira ticket or not, has the same md set from _templates.
- Project paused: start "## Now working on" with PENDING (who, date): reason
- Never edit the dashboard note.md by hand. The hooks keep it in sync.
  If a hook asks, run the project_note.py command it gives you.
```

**6. Trust the folder once.** Open `work_jira` in VS Code and start Claude. When Claude Code asks
whether you trust this folder, say yes. Hooks only run in trusted folders, and trusting `work_jira`
covers the project folders inside it.

**7. Check it.** In the Claude panel type `/hooks`. You should see one `Stop` and one `SessionStart`
hook, both running `work_jira_hooks.py`.

### The tracking_log.md headings the hooks read

The hooks copy from these headings in each project's `tracking_log.md` (the layout in `_templates`):

```markdown
## Now working on
PENDING (you, 2026-10-22): waiting for the lab slot.  <!-- only when paused -->

## Next up
What comes next, one or more lines.

## Last update
2026-10-22 — what was done
```

If a heading is missing, the Stop hook asks Claude once to put it back. You can also update a card
by hand at any time: `.venv\Scripts\python project_note.py sync ABC-123`.

---

## When something is wrong

Run `.venv\Scripts\python check_setup.py` first. The most common answers:

| You see | Do this |
|---|---|
| `... has spaces in it` | You pasted something other than the token (often the command itself). Set it again and paste only the token. |
| `Claude login failed` | The Claude token is wrong or expired. Get a fresh one and set it again. |
| `No Claude login found` | You're in a new window: set the Claude variables again (Part 2, step 2). |
| `Packages: ...` | Run `.venv\Scripts\python -m pip install -r requirements.txt` |
| `missing permissions` | Your Slack app was made by hand and missed some. Easiest fix: make a new app from the manifest (Step 5). |
| `the instant connection did not open` | The work network may block it. Put `slack_mode=backup` in `settings.ini`: the app then checks Slack every 30 seconds instead. |
| Slack button says "reconnecting…" for minutes | Same as above: `slack_mode=backup`. |
| A card doesn't follow its work_jira folder | Check you opened the project folder itself in VS Code (not all of `work_jira`), the folder is trusted, and `/hooks` shows both hooks. Then run `.venv\Scripts\python project_note.py sync <ID>` to see the error in plain English. |
| A message starting `work_jira hook` in the Claude panel | The hook hit a problem; Claude carries on. The message says what. Often `settings.ini` was moved or a note.md is open in another program. |
| `Address already in use` or `WinError 10048` | The app is already running in another PowerShell window. Use that one, or close it first. |

## Get the newest version

```powershell
cd $HOME\Desktop\work-assistant
git pull
.venv\Scripts\python -m pip install -r requirements.txt
```

Then start the app as usual. Your `settings.ini` and your projects are never touched by an update.

---

## On a work Mac

Same steps as Windows, with these differences:

- Use **Terminal** instead of PowerShell.
- On a Mac the command is `python3`, not `python`. So:
  - make the `.venv` with `python3 -m venv .venv`
  - use `.venv/bin/python3` everywhere the Windows steps say `.venv\Scripts\python`
    (for example `.venv/bin/python3 check_setup.py` and `.venv/bin/python3 app.py`)
- Use `cp` instead of `copy`, and `open -e settings.ini` instead of `notepad settings.ini`.

**Claude login (Part 1, Step 4).** Check whether it's already set:

```bash
echo $ANTHROPIC_BASE_URL
```

It prints an address: nothing to do. It prints nothing: set both variables each time you start the
app (below), the same way as on Windows.

**Setting tokens (Part 2, step 2).** Run each line on its own. The `read -s` lines wait
**silently**: paste the token (you'll see nothing), press Enter.

```bash
read ANTHROPIC_BASE_URL && export ANTHROPIC_BASE_URL
read -s ANTHROPIC_AUTH_TOKEN && export ANTHROPIC_AUTH_TOKEN
read -s SLACK_USER_TOKEN && export SLACK_USER_TOKEN
read -s SLACK_APP_TOKEN && export SLACK_APP_TOKEN
```

(Skip the first two if the address was already set; skip the Slack lines if you don't use Slack.
The gateway address isn't secret, so its line shows what you paste.)

Careful: copy the **token** before you run a `read -s` line, not the line itself. Pasting the command
by mistake is easy because nothing shows; `check_setup.py` will tell you if it happened
("has spaces in it").

Like on Windows, these last only for that Terminal window.

## For developers

- Tests: `.venv\Scripts\python -m pytest` (Mac: `.venv/bin/python3 -m pytest`). They use fake Claude and
  fake Slack clients, so they never need the network or a token.
- This repo is **public**: never commit tokens, real Slack IDs, or company URLs.
