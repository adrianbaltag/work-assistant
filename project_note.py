"""Keep dashboard cards in step with project folders in work_jira. Pure Python, no Flask.

Work Claude runs it (when a hook asks), and the hooks in work_jira_hooks.py call it:

    python project_note.py create ABC-123 --title "Alarm update" --goal "One or two lines"
    python project_note.py sync   ABC-123

Each work_jira project folder has a tracking_log.md with three sections:
    ## Now working on   -> status (PENDING ... = pending + blocked_by)
    ## Next up          -> next:
    ## Last update      -> one "date · Claude · text" history line
Paths come from settings.ini: projects_folder= and work_jira_folder=.
"""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import notes

TRACKING_LOG = "tracking_log.md"
SOURCE = "work_jira"        # source: work_jira = this card follows a work_jira folder (and may be auto-archived)
WHO = "Claude"
MOVED_TO_PROD = "Folder left work_jira (moved to prod): archived automatically"
SECTIONS = {"now working on": "now", "next up": "next", "last update": "last"}
HEADINGS = {"now": "## Now working on", "next": "## Next up", "last": "## Last update"}


class SyncError(Exception):
    """tracking_log.md is missing or does not have the three headings. The message says what to fix."""


class NoCard(Exception):
    """The project has no open dashboard card yet."""


# ---------- reading tracking_log.md ----------

def read_tracking_log(text):
    """The three sections of tracking_log.md as one-line texts: {"now": ..., "next": ..., "last": ...}."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)       # the rules comment at the top is not content
    found, key = {}, None
    for line in text.splitlines():
        if line.startswith("#"):
            key = SECTIONS.get(line.lstrip("#").strip().lower())     # None for headings we don't use
            if key:
                found[key] = []
        elif key:
            found[key].append(line.strip())
    missing = [HEADINGS[k] for k in HEADINGS if k not in found]
    if missing:
        raise SyncError(f"tracking_log.md has no {', '.join(missing)} heading. "
                        "Put the headings back (as in _templates), then run project_note.py sync again.")
    return {k: " ".join(part for part in lines if part) for k, lines in found.items()}


def status_from(now_working_on):
    """(status, blocked_by) from "## Now working on". "PENDING (who, date): reason. More." = pending."""
    text = now_working_on.strip()
    if not re.match(r"pending\b", text, re.I):
        return "active", ""
    rest = re.sub(r"^\s*\([^)]*\)", "", text[len("pending"):])    # drop "(user, 2026-10-22)"
    rest = rest.lstrip(" :—–-")
    sentence = re.match(r"(.+?[.!?])(\s|$)", rest)              # the first sentence is the reason
    return "pending", sentence.group(1) if sentence else rest


def last_update(text, now):
    """(date, text) from "## Last update", e.g. "2026-10-21 — M1 ticked". No date = today. Empty = None."""
    text = text.strip()
    if not text:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})\s*[—–-]+\s*(.*)", text)
    return match.groups() if match else (now.strftime("%Y-%m-%d"), text)


# ---------- which folder is a work_jira project ----------

def same_folder(a, b):
    return os.path.normcase(str(a)) == os.path.normcase(str(b))     # Windows: case does not matter


def work_project(work_jira_folder, cwd):
    """The project folder (right under work_jira) that cwd is in, or None.

    Claude may have cd'd deeper (e.g. into tests\\), so we walk up. _templates and hidden folders are not projects.
    """
    if not str(work_jira_folder).strip():
        return None
    work_jira = Path(work_jira_folder).resolve()
    here = Path(cwd).resolve()
    for folder in [here, *here.parents]:
        if same_folder(folder.parent, work_jira) and folder != folder.parent:
            return None if folder.name.startswith(("_", ".")) else folder
    return None


# ---------- sync: tracking_log.md -> dashboard card ----------

def sync(projects_folder, work_folder, now):
    """Copy next / status / blocked_by and a new history line from tracking_log.md into the card."""
    log_file = Path(work_folder) / TRACKING_LOG
    if not log_file.is_file():
        raise SyncError(f"No {TRACKING_LOG} in {work_folder}. Create it from _templates first.")
    log = read_tracking_log(log_file.read_text(encoding="utf-8-sig"))
    card = notes.find_project(projects_folder, Path(work_folder).name)
    if card is None:
        raise NoCard(Path(work_folder).name)

    note = card / notes.NOTE_FILE
    text = note.read_text(encoding="utf-8-sig")
    status, blocked_by = status_from(log["now"])
    text = notes.set_fields(text, {"next": log["next"], "status": status, "blocked_by": blocked_by,
                                   "source": SOURCE, "folder": str(work_folder)})
    entry = last_update(log["last"], now)
    if entry and not already_in_history(text, *entry):
        text = notes.add_history(text, entry[1], entry[0], who=WHO)
    note.write_text(text, encoding="utf-8")     # always written, so the card is now newer than the log
    return card


def already_in_history(text, date, said):
    said = " ".join(said.split())
    return any(h["date"] == date and h["who"] == WHO and h["text"] == said for h in notes.read_history(text))


def needs_sync(card, work_folder):
    """True when tracking_log.md changed after the card was last written."""
    log_file = Path(work_folder) / TRACKING_LOG
    note = Path(card) / notes.NOTE_FILE
    return log_file.is_file() and log_file.stat().st_mtime_ns > note.stat().st_mtime_ns


# ---------- create: a new card (or bring an archived one back) ----------

def create(projects_folder, work_folder, title, goal, now):
    """Make sure the work_jira project has a filled dashboard card. Returns (card folder, what happened).

    what = "exists"   (it had one: just synced)
           "restored" (its card was in the Archive, e.g. the folder came back from prod)
           "created"  (a new card, made by the same code as the app's + New project)
    """
    name = Path(work_folder).name
    card = notes.find_project(projects_folder, name)
    if card:
        what = "exists"
    elif newest_archived(projects_folder, name):
        notes.restore_project(projects_folder, newest_archived(projects_folder, name), now, name=name)
        card, what = Path(projects_folder) / name, "restored"
    else:
        card, what = notes.new_project(projects_folder, name, title), "created"
        if goal.strip():
            note = card / notes.NOTE_FILE
            text = note.read_text(encoding="utf-8")
            note.write_text(text.replace("## Goal\n", f"## Goal\n{goal.strip()}\n", 1), encoding="utf-8")

    if (Path(work_folder) / TRACKING_LOG).is_file():
        sync(projects_folder, work_folder, now)
    else:                                   # created before the md set exists: just link the card
        note = card / notes.NOTE_FILE
        note.write_text(notes.set_fields(note.read_text(encoding="utf-8-sig"),
                                         {"source": SOURCE, "folder": str(work_folder)}), encoding="utf-8")
    return card, what


def newest_archived(projects_folder, name):
    """The newest archived card for this name ("ABC-1" or "ABC-1 (2026-10-24 10-00)"), or None."""
    archive = Path(projects_folder) / notes.ARCHIVE_FOLDER
    found = [f for f in (archive.iterdir() if archive.is_dir() else [])
             if (f.name == name or f.name.startswith(name + " (")) and (f / notes.NOTE_FILE).is_file()]
    return max(found, key=lambda f: (f / notes.NOTE_FILE).stat().st_mtime_ns, default=None)


# ---------- archive check: folders that left work_jira ----------

def archive_gone(projects_folder, work_jira_folder, now):
    """Archive every work_jira card whose folder is no longer in work_jira (moved to prod). Returns their IDs.

    Does nothing when work_jira is missing, unreadable or has no project folders: better no archive than a wrong one.
    Cards without source: work_jira (personal ideas, + New project unticked) are never touched.
    """
    if not str(work_jira_folder).strip():
        return []
    try:
        here = {f.name.casefold() for f in Path(work_jira_folder).iterdir()
                if f.is_dir() and not f.name.startswith(("_", "."))}
    except OSError:
        return []
    if not here:
        return []
    archived = []
    for project in notes.list_projects(projects_folder):
        if project.get("source") == SOURCE and project["id"].casefold() not in here:
            try:
                notes.archive_project(projects_folder, Path(projects_folder) / project["id"], now, said=MOVED_TO_PROD)
            except OSError:
                continue        # a file is open (e.g. in Excel): try again next session
            archived.append(project["id"])
    return archived


# ---------- command line ----------

def main(argv, settings_path=notes.SETTINGS_FILE, now=None):
    """Run "create" or "sync" for one project folder name. Returns 0 (ok) or 1 (error, message on stderr)."""
    parser = argparse.ArgumentParser(prog="project_note.py", description="Keep a dashboard card in step with work_jira.")
    parser.add_argument("action", choices=["create", "sync"])
    parser.add_argument("name", help="the project folder name in work_jira, e.g. ABC-123")
    parser.add_argument("--title", default="", help="create: short project name for the card")
    parser.add_argument("--goal", default="", help="create: one or two lines for the card's Goal")
    args = parser.parse_args(argv)
    now = now or datetime.now()

    try:
        settings = notes.load_settings(settings_path)
    except SystemExit as err:
        return fail(str(err))
    projects_folder = settings.get("projects_folder", "").strip()
    work_jira = settings.get("work_jira_folder", "").strip()
    if not work_jira:
        return fail("settings.ini has no work_jira_folder=. Add it: the folder that holds your project folders.")
    work = Path(work_jira) / args.name
    if not notes.plain_name(args.name) or not work.is_dir():
        return fail(f"No folder {args.name} in {work_jira}. Use the project folder's exact name.")

    try:
        if args.action == "create":
            card, what = create(projects_folder, work, args.title, args.goal, now)
            print({"created": f"Dashboard card {args.name} created and filled from {TRACKING_LOG}.",
                   "restored": f"Dashboard card {args.name} brought back from the Archive and updated.",
                   "exists": f"Dashboard card {args.name} already existed: updated it."}[what])
        else:
            sync(projects_folder, work, now)
            print(f"Dashboard card {args.name} updated from {TRACKING_LOG}.")
    except NoCard:
        return fail(f"{args.name} has no dashboard card yet. Run: project_note.py create {args.name} "
                    '--title "short name" --goal "one or two lines"')
    except SyncError as err:
        return fail(str(err))
    except FileExistsError:
        return fail(f"Something named {args.name} is already in {projects_folder} but it is not a card "
                    "(no note.md). Rename or move it, then try again.")
    except OSError as err:
        return fail(f"Could not update the card ({err.strerror}). Is note.md open in another program? "
                    "Close it and try again.")
    return 0


def fail(message):
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")    # Windows pipes default to an old code page
    sys.exit(main(sys.argv[1:]))
