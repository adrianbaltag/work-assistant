"""Claude Code hooks that keep the dashboard in step with work_jira. Pure Python, no Flask, no tokens.

Set up once in your user settings (~/.claude/settings.json, see README):
    python work_jira_hooks.py stop            after every Claude reply
    python work_jira_hooks.py session-start   when a Claude Code session starts

Claude Code sends the hook a small JSON on stdin (we use "cwd" = the folder Claude is in).
Exit 0 = all fine. Exit 2 (Stop only) = Claude must keep going: our stderr message tells it what to do.
Any other problem = exit 1, which Claude Code shows but never blocks on.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import notes
import project_note as pn

HELPER = Path(__file__).with_name("project_note.py")

CREATE_CARD = """This project has no dashboard card yet. Create it now with one command, then carry on:
  {python} {helper} create {name} --title "<short project name>" --goal "<one or two lines: what this project must achieve>"
Don't edit the dashboard note.md by hand: the hooks keep it in sync."""

NEW_FOLDER = """This is a new project folder: {name}. Before anything else, set it up with the same md set every \
project has, copied from {templates} (CLAUDE.md, requirements.md, tracking_log.md and the rest).{ticket} \
Then run the clear-requirements skill, then grill-me. Once tracking_log.md exists, a hook keeps the dashboard card in sync."""

READ_TICKET = " Read ticket.md first: it holds the Jira description the user pasted."

OLD_FOLDER = """This project folder ({name}) is missing its md set (no tracking_log.md). Before other work, create \
the missing md files from {templates}, filled in from what is already in the folder. \
Do not run clear-requirements or grill-me unless the user asks."""


def stop(event, settings, now):
    """After every Claude reply. Returns (exit code, message for Claude)."""
    projects, work_jira = settings_paths(settings)
    cwd = event.get("cwd") or os.getcwd()
    work = pn.work_project(work_jira, cwd)
    if work is None:
        if work_jira and pn.same_folder(Path(cwd).resolve(), Path(work_jira).resolve()):
            sync_all(projects, work_jira, now)       # whole work_jira open (old way): sync quietly, never ask
        return 0, ""
    if not (work / pn.TRACKING_LOG).is_file():
        return 0, ""                                 # still being set up: SessionStart already said what to do
    blocked_ok = not event.get("stop_hook_active")   # never block twice in a row (no loops)

    try:
        card = notes.find_project(projects, work.name)
        if card is None and pn.newest_archived(projects, work.name):
            pn.create(projects, work, "", "", now)   # folder came back from prod: restore the card, no Claude needed
        elif card is None:
            return (2, CREATE_CARD.format(python=quoted(sys.executable), helper=quoted(HELPER), name=work.name)) \
                if blocked_ok else (0, "")
        elif pn.needs_sync(card, work):
            pn.sync(projects, work, now)
    except pn.SyncError as err:
        return (2, f"Dashboard sync: {err}") if blocked_ok else (0, "")
    return 0, ""


def sync_all(projects, work_jira, now):
    """Sync every card whose work_jira folder has a newer tracking_log.md. Problems are skipped silently."""
    for folder in Path(work_jira).iterdir():
        card = notes.find_project(projects, folder.name)
        if card and folder.is_dir() and not folder.name.startswith(("_", ".")) and pn.needs_sync(card, folder):
            try:
                pn.sync(projects, folder, now)
            except (pn.SyncError, OSError):
                pass


def session_start(event, settings, now):
    """When a session starts. Returns (context for Claude, note for the user); "" = nothing to say."""
    projects, work_jira = settings_paths(settings)
    gone = pn.archive_gone(projects, work_jira, now)
    for_user = (f"Dashboard: moved {', '.join(gone)} to the Archive page (folder no longer in work_jira)."
                if gone else "")

    work = pn.work_project(work_jira, event.get("cwd") or os.getcwd())
    if work is None or (work / pn.TRACKING_LOG).is_file():
        return "", for_user
    files = {f.name for f in work.iterdir() if not f.name.startswith(".")}
    templates = Path(work_jira) / "_templates"
    if files <= {"ticket.md"}:
        ticket = READ_TICKET if files else ""
        return NEW_FOLDER.format(name=work.name, templates=templates, ticket=ticket), for_user
    return OLD_FOLDER.format(name=work.name, templates=templates), for_user


def settings_paths(settings):
    return settings.get("projects_folder", "").strip(), settings.get("work_jira_folder", "").strip()


def quoted(path):
    path = str(path)
    return f'"{path}"' if " " in path else path


def main(argv, stdin=sys.stdin, settings_path=notes.SETTINGS_FILE, now=None):
    which = argv[0] if argv else ""
    try:
        raw = stdin.buffer.read().decode("utf-8") if hasattr(stdin, "buffer") else stdin.read()
        event = json.loads(raw or "{}")
    except ValueError:
        event = {}
    try:
        settings = notes.load_settings(settings_path)
        if which == "stop":
            code, message = stop(event, settings, now or datetime.now())
            if message:
                print(message, file=sys.stderr)
            return code
        if which == "session-start":
            context, for_user = session_start(event, settings, now or datetime.now())
            out = {}
            if context:
                out["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": context}
            if for_user:
                out["systemMessage"] = for_user
            if out:
                print(json.dumps(out))
            return 0
        print("work_jira_hooks.py needs one word: stop or session-start", file=sys.stderr)
        return 1
    except SystemExit as err:            # settings.ini missing
        print(f"work_jira hook: {err}", file=sys.stderr)
        return 1
    except Exception as err:             # never block Claude because of a bug or a locked file here
        print(f"work_jira hook problem (Claude can carry on): {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")    # Windows pipes default to an old code page
    sys.exit(main(sys.argv[1:]))
