# Work Assistant — project rules

Local Flask page over the user's project notes: dashboard + CRUD, Ask Claude, Slack button.
Runs on each colleague's own WORK laptop (Windows, Python 3.10). Built and tested on the Mac first.
Setup steps for people: README.md. Parked ideas and known gaps: TODO.md.

## Run and test

- Tests: `.venv/bin/python -m pytest` (Mac). All must pass before any commit.
- App: `.venv/bin/python app.py` → http://127.0.0.1:5050. Restart it after every code change.
- Setup check with real logins: `.venv/bin/python check_setup.py` (sends one tiny real Claude message).

## Files

- `app.py`: Flask routes, `load_settings`, `create_app` (fakes injected in tests).
- `notes.py`: note.md parsing and file ops, pure Python, no Flask.
- `claude_chat.py`: Ask Claude; `plain_error` = the one place for Claude error wording.
- `slack_inbox.py`: Slack rules (what glows, rows, catch-up, read check), no threads; `plain_error` for Slack.
- `slack_live.py`: Slack background part (Socket Mode / backup polling, rate gate).
- `check_setup.py`: setup checks; `SLACK_SCOPES` must match `slack-app-manifest.json` (a test enforces it).
- `static/*.js`, `templates/index.html`: the page. The user doesn't write JS: keep it plain and commented.

## Rules

- PUBLIC repo: never commit tokens, real Slack workspace/user/channel IDs, or company URLs. Tests use made-up IDs.
- Target = Windows PowerShell + Python 3.10: no 3.11+ syntax; paths via pathlib; README commands in PowerShell.
- Tests never touch the network: Claude and Slack clients are always fakes passed in.
- Every error a person can see is plain English and says what to do.
- `settings.ini` = key=value lines, no [section]; it is gitignored. New settings go in `settings.ini.example` with a comment.
- Logins only from environment variables, never from a file.
- Claude calls: basic Messages API only (the work gateway may not support betas or strict tools).
- Slack: one app per person (Socket Mode spreads events across every connected copy of an app).

<!-- handoffs/ (gitignored) holds session handoffs and probe logs with real IDs: never commit it. -->
<!-- The Stop hook in .claude/settings.local.json is Mac-only, so it lives in a gitignored file. -->
