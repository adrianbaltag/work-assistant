# TODO

Known things, found in reviews and real tests, that are parked on purpose. Each line says why.

## Slack button

- **Opened rows can come back.** `Inbox.opened()` keeps no memory, so a row you clicked can return
  in a backup round or catch-up if Slack's read mark didn't move. Rare: clicking opens Slack, which
  marks it read.
- **Thread row with no thread read mark never clears.** Catch-up then uses the channel's read mark;
  the live part doesn't. Not reachable in practice: tested on real Slack 2026-10-21, a thread
  mention (also a group one) subscribes you, so Slack gives the thread's read mark.
- **Any reconnect = a full catch-up.** Every socket drop (also Slack's routine refresh) asks about
  every DM you ever had, plus the searches. Fine for under ~20 DMs (~30 s "checking…"). Fix if heavy
  users need it: catch up only from the time of the drop.
- **Gate doesn't hold callers already waiting.** `Gate._hold` (after "too many calls") doesn't delay
  calls that already have their turn, so they can hit Slack's wait window and use up their tries.
- **Backup round can go over the call budget.** `dm_batch` counts one call per DM, but checking a DM
  is 2+ calls and a search can be up to 5 pages. The gate still keeps the per-minute limit.
- **A long read check pauses the ticker.** The read check runs on the ticker thread, 1.5 s per call,
  so 40 unread conversations = ~60 s when a dropped connection isn't noticed. Fix if needed: run it
  on its own thread like catch-up.
- **slack_sdk errors are silent.** It logs to nowhere (NullHandler), so a stuck reconnect leaves no
  trace. To be covered in the logging lesson.

## Setup check (check_setup.py)

- **Unverified Slack button labels in README.** "Generate Token and Scopes" and "Request to Install"
  were written from memory: check them the next time an app is made (office).

## work_jira sync

- **Archive message not seen in VS Code.** Office test 2026-10-23: the SessionStart hook archived
  TEST-1 correctly, but "Dashboard: moved ... to the Archive page" never showed in the VS Code
  Claude chat. Confirmed 2026-10-23: the terminal CLI (`claude` in PowerShell) DOES show the line,
  so the hook works and only the VS Code extension hides hook `systemMessage`. Nothing to fix in our code.
- **Lowercase ticket cards imported before the fix still have an empty `jira:`.** New imports now fill it
  (`project_note.fill_jira`); an old card gets it the next time `project_note.py create` runs for its
  folder. Sync and Import never touch `jira:` on an existing card: add `fill_jira` to `sync_all` if
  that matters.
- **Import and Stop each hold a copy of the "archived by you vs moved to prod" rule**
  (`import_missing`, `stop`). If one changes, change both, or move it into one helper.
- **The gate's stop still shows in red, with "Error:".** Tried 2026-11-16: Claude Code shows every
  stopped write that way. The gate now answers with a "deny" instead of exit 2, which takes the hook's
  long file path out of the line. On Claude Code 2.1.267 (Windows) the line is then
  `Error: Not written: ...`. On 2.1.326 (Mac) it still says `PreToolUse:Write hook error:` before our
  message. Nothing more to fix in our code.

## Dashboard

- **A bad note's message sits in the "working on" column.** A note that is not UTF-8 shows as its own row
  and the fix-it text is carried in `working_on` (and in a `problem` field the page does not draw yet).
  Fix if needed: draw `problem` on the row and on the card in its own style.
- **Hand-typed `priority: High` (capital) or `low` is missed by the Priority filter.** The filter,
  the tiles and the pills all match the exact lowercase words the card writes. Not reachable when
  notes are changed from the card (found in review 2026-10-31). Fix if needed: lowercase status
  and priority when notes.py reads a note.
- **Folder errors are not logged.** The plain messages for a projects folder or work_jira folder
  that can't be opened (`api_projects`, `work_jira_problem` in app.py) show on the page but leave
  no log line. Same for Ask Claude's "can't open / can't read" work folder files (`project_context` in
  claude_chat.py) and an unreadable ticket.md (`ticket_goal` in project_note.py). The project has no
  logging yet: add them in the logging lesson (decided 2026-11-06).
- **Three tests can fail when run exactly across midnight.** Seen once, 2026-11-18 23:59: 3 unit tests
  failed, then passed on every later run. Some tests compare with the real date (`datetime.now()` in
  `tests/test_app.py`). The names were not caught; if it shows again, note them and give those tests a fixed clock.
- **The dashboard's message files are never cleaned up.** Every Note / Blocker / Unblock stays as a small
  file in the project folder's `.claude\dashboard-inbox`, and the hooks read all of them at every prompt.
  Fine for hundreds; add a clean-up of old, finished messages if a folder ever gets thousands.
- **"seen by Claude" is not live on an open card.** It changes when the card is opened again or after the
  next send (the 30-second refresh does not touch an open card).

## To do page

- **Two todos with the same words + two tabs can hit the wrong one.** A change names a todo by its
  row + words. If another tab deletes a todo above two same-worded todos, the old tab's click can land
  on the other one. Not reachable in practice: one tab, no duplicate todos (decided 2026-10-30).
  Fix if needed: every answer carries a stamp of the file; any change from an out-of-date page = 409.
- **Hand-typed lines like `- [x](link) notes` become todos.** The parser accepts near misses
  (`* [ ] x`, `- [ ]x`) so it also reads some markdown links as todos. Not reachable: todos.md is
  only changed from the page, never by hand (decided 2026-10-30).
- **A crash mid-save could still leave todos.md short.** The text is encoded before the file is
  opened, so a bad character can't empty it any more; only a power cut / full disk during the write
  could. Fix if needed: write a temp file then os.replace (check it works on Windows when the file
  is open elsewhere).

## ticket-flow plugin

- **`python` on a work Mac.** The plugin's hooks start with the plain command `python` (tested on
  Windows and on one Mac). A Mac that only has `python3` cannot start them. Not tried on a work Mac yet.
- **The gate only sees Claude's file tools.** A file written by a shell command is not stopped; the
  review's git diff is the backstop. Code kept outside the ticket folder is not checked at all.
- **The gate is a guard rail, not a lock.** Claude can write the `Status` and `Plan approved by` lines
  itself, since `requirements.md` is a note. Accepted 2026-11-15, and said in the README. A stronger
  guard (Claude Code asks you before one of those two lines is written) is possible later: first check
  that it works on the work laptop's Claude Code version.
- **No log file for the hooks.** When the starter cannot find the app folder, or a file cannot be
  read, you see one line on screen and nothing is saved. Decided 2026-11-15: the log file comes with
  the logging lesson, for the whole app at once.
- **check_setup.py reads Claude Code's plugin list file.** `plugins/installed_plugins.json` is not in
  the Claude Code docs, so its layout may change. If it does, the check says "could not tell" and
  nothing breaks. The documented way is `claude plugin list --json`.
- **Read in place, the recorded version can be old.** On the work laptop the plugin is read from the
  app folder, so new files are used right after `git pull`, but check_setup.py may still warn about
  the version until `claude plugin update` is run. Check this in the live try.
