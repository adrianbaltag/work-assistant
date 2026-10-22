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
