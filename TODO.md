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

- **One shared settings check.** check_setup.py re-runs create_app's checks piece by piece, so a new
  setting must be added in both places. Also app.py itself still shows a raw traceback when
  projects_folder= is missing (KeyError) or settings.ini has an unreadable line. Fix: one
  `validate_settings()` in app.py that both use.
- **Unverified Slack button labels in README.** "Generate Token and Scopes" and "Request to Install"
  were written from memory: check them the next time an app is made (office).

## work_jira sync

- **Archive message not seen in VS Code.** Office test 2026-10-23: the SessionStart hook archived
  TEST-1 correctly, but "Dashboard: moved ... to the Archive page" never showed in the VS Code
  Claude chat. Likely the extension doesn't display hook `systemMessage`. Check in the terminal CLI
  before changing anything.
- **Lowercase ticket folders import as lowercase cards.** A folder `work_jira\abc-123` gets card
  `abc-123` with an empty `jira:` (no Jira button), unlike + New project, which uppercases.
  Fix idea: rename the folder to capitals, or fill `jira:` with the uppercased name on import.
- **Import and Stop each hold a copy of the "archived by you vs moved to prod" rule**
  (`import_missing`, `stop`). If one changes, change both, or move it into one helper.
