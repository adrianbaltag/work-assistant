"""Keep dashboard cards in step with project folders in work_jira. Pure Python, no Flask.

Work Claude runs it (when a hook asks), and the hooks in work_jira_hooks.py call it:

    python project_note.py create ABC-123 --title "Alarm update" --goal "One or two lines"
    python project_note.py sync   ABC-123

Each work_jira project folder has a tracking_log.md with three sections:
    ## Now working on   -> status (PENDING ... = pending + blocked_by)
    ## Next up          -> next:
    ## Last update      -> "date · Claude · text" history line(s) from the newest-dated line(s)
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
BACK_FROM_PROD = "Folder back in work_jira: restored automatically"
RESTORED_BY_HAND = "Restored from archive"          # the app's Restore button (notes.restore_project)
CARD_EVENTS = {MOVED_TO_PROD, BACK_FROM_PROD, RESTORED_BY_HAND, "Marked done and archived"}
SECTIONS = {"now working on": "now", "next up": "next", "last update": "last"}
HEADINGS = {"now": "## Now working on", "next": "## Next up", "last": "## Last update"}


class SyncError(Exception):
    """tracking_log.md is missing or does not have the three headings. The message says what to fix."""


class NoCard(Exception):
    """The project has no open dashboard card yet."""


# ---------- reading tracking_log.md ----------

def read_tracking_log(text):
    """The sections of tracking_log.md: {"now": one line, "next": one line, "last": [lines]}.

    Only "# " and "## " lines are headings: "### Phase 2" or "#42 needs review" are part of the section.
    "last" = the line(s) with the newest "YYYY-MM-DD — " date, wherever they are in the section
    (Claude may add new entries at the top or the bottom). No dated line = the first line. Empty = [].
    """
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)       # the rules comment at the top is not content
    found, key = {}, None
    for line in text.splitlines():
        if re.match(r"#{1,2}\s", line):
            key = SECTIONS.get(line.lstrip("#").strip().lower())     # None for headings we don't use
            if key:
                found[key] = []
        elif key:
            found[key].append(line.strip())
    missing = [HEADINGS[k] for k in HEADINGS if k not in found]
    if missing:
        raise SyncError(f"tracking_log.md has no {', '.join(missing)} heading. "
                        "Put the headings back (as in _templates), then run project_note.py sync again.")
    log = {k: " ".join(part for part in lines if part) for k, lines in found.items()}
    lines = [part for part in found["last"] if part]
    dates = [last_update(part, None)[0] for part in lines]
    newest = max((d for d in dates if d), default=None)          # "YYYY-MM-DD" sorts like a date
    log["last"] = [part for part, d in zip(lines, dates) if d == newest] if newest else lines[:1]
    return log


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
    """(date, text) from "## Last update", e.g. "2026-10-21 — M1 ticked". No date = (None, text). Empty = None."""
    text = re.sub(r"^[-*]\s+", "", text.strip())             # "- 2026-10-21 — x" written as a bullet
    if not text:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})\s*[—–-]+\s*(.*)", text)
    return match.groups() if match else (None, text)


# ---------- which folder is a work_jira project ----------

def same_folder(a, b):
    return os.path.normcase(str(a)) == os.path.normcase(str(b))     # Windows: case does not matter


def is_project_folder(path):
    """A work_jira project folder: a folder whose name doesn't start with _ (e.g. _templates) or . (e.g. .claude)."""
    path = Path(path)
    return not path.name.startswith(("_", ".")) and path.is_dir()


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
            return folder if is_project_folder(folder) else None
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
    for line in reversed(log["last"]):        # each goes on top, so reversed keeps tracking_log's order
        entry = last_update(line, now)
        if not already_in_history(text, *entry):
            text = notes.add_history(text, entry[1], entry[0] or now.strftime("%Y-%m-%d"), who=WHO)
    note.write_text(text, encoding="utf-8")     # always written, so the card is now newer than the log
    return card


def already_in_history(text, date, said):
    """date None (the line had no date) = the same text on any day counts."""
    said = " ".join(said.split())
    return any((date is None or h["date"] == date) and h["who"] == WHO and h["text"] == said
               for h in notes.read_history(text))


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
    archived = None if card else newest_archived(projects_folder, name)
    if card:
        what = "exists"
    elif archived:
        if (Path(projects_folder) / name).exists():       # a stray folder or file: restoring would add a suffix
            raise FileExistsError(name)
        notes.restore_project(projects_folder, archived, now, name=name, said=BACK_FROM_PROD)
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
        link_card(card, work_folder)
    return card, what


def link_card(card, work_folder):
    """Mark the card as following this work_jira folder (source: + folder:)."""
    note = Path(card) / notes.NOTE_FILE
    note.write_text(notes.set_fields(note.read_text(encoding="utf-8-sig"),
                                     {"source": SOURCE, "folder": str(work_folder)}), encoding="utf-8")


def start_work_folder(work_jira_folder, name, description, created_by):
    """The app's + New project with "Work project" ticked: make work_jira\\<name>\\ and its ticket.md.

    Returns (folder, made). An existing folder is never touched (made = False).
    No description and no "created by" = an empty folder. Raises FileNotFoundError if work_jira is missing.
    """
    work_jira = Path(work_jira_folder)
    if not work_jira.is_dir():
        raise FileNotFoundError(2, "folder not found", str(work_jira))
    folder = work_jira / name
    if folder.exists():
        return folder, False
    folder.mkdir()
    description = "\n".join(description.strip().splitlines())      # pasted text may have Windows line ends
    created_by = created_by.strip()
    if description or created_by:
        (folder / "ticket.md").write_text(f"# {name}\n\nCreated by: {created_by}\n\n"
                                          f"## Description (pasted from Jira)\n{description}\n", encoding="utf-8")
    return folder, True


def last_event(note_file):
    """The newest archive/restore line in a card's History (e.g. MOVED_TO_PROD), or "" if none.

    A sync line from Claude newer than it counts as an event too ("" back): the folder was worked on since.
    """
    history = notes.read_history(Path(note_file).read_text(encoding="utf-8-sig"))
    return next((h["text"] if h["text"] in CARD_EVENTS else "" for h in history
                 if h["text"] in CARD_EVENTS or h["who"] == WHO), "")


def newest_archived(projects_folder, name):
    """The newest archived card for this name ("ABC-1" or "ABC-1 (2026-10-24 10-00)"), or None.

    Capitals don't count (abc-1 = ABC-1), as on Windows.
    """
    archive = Path(projects_folder) / notes.ARCHIVE_FOLDER
    name = name.casefold()
    found = [f for f in (archive.iterdir() if archive.is_dir() else [])
             if (f.name.casefold() == name or f.name.casefold().startswith(name + " ("))
             and (f / notes.NOTE_FILE).is_file()]
    return max(found, key=lambda f: (f / notes.NOTE_FILE).stat().st_mtime_ns, default=None)


# ---------- archive check: folders that left work_jira ----------

def archive_gone(projects_folder, work_jira_folder, now):
    """Archive every work_jira card whose folder is no longer in work_jira (moved to prod). Returns their IDs.

    Does nothing when work_jira is missing, unreadable or has no project folders: better no archive than a wrong one.
    Cards without source: work_jira (personal ideas, + New project unticked) are never touched,
    nor a card you brought back yourself with Restore (until it is archived again).
    Reads only each note.md, not every file in every project: this runs at every session start.
    """
    if not str(work_jira_folder).strip():
        return []
    try:
        here = {f.name.casefold() for f in Path(work_jira_folder).iterdir() if is_project_folder(f)}
    except OSError:
        return []
    if not here:
        return []
    archived = []
    for card in sorted(Path(projects_folder).iterdir()):
        note = card / notes.NOTE_FILE
        if card.name == notes.ARCHIVE_FOLDER or card.name.startswith(".") or card.name.casefold() in here:
            continue
        try:
            if not note.is_file() or notes.parse_note(note.read_text(encoding="utf-8-sig"))[0].get("source") != SOURCE:
                continue
            if last_event(note) == RESTORED_BY_HAND:
                continue
            notes.archive_project(projects_folder, card, now, said=MOVED_TO_PROD)
        except OSError:
            continue            # a file is open (e.g. in Excel): try again next session
        archived.append(card.name)
    return archived


# ---------- import: a card for every work_jira folder ----------

def import_missing(projects_folder, work_jira_folder, now):
    """Make a card for every work_jira project folder that has none. Returns their IDs, A-Z.

    Rule: every folder in work_jira has a card, on the Dashboard or on the Archive page.
    A card you archived yourself stays archived; one archived because the folder left (prod) comes back.
    No tracking_log.md yet = a bare card (title = folder name), filled in once Claude works in the folder.
    A card that can't be made (a stray file has the name, a file is open) is skipped: tried again next session.
    """
    if not str(work_jira_folder).strip():
        return []
    try:
        folders = sorted(f for f in Path(work_jira_folder).iterdir() if is_project_folder(f))
    except OSError:
        return []
    added = []
    for folder in folders:
        try:
            if notes.find_project(projects_folder, folder.name):
                continue
            archived = newest_archived(projects_folder, folder.name)
            if archived and last_event(archived / notes.NOTE_FILE) != MOVED_TO_PROD:
                continue                                    # you archived it yourself
            create(projects_folder, folder, "", "", now)
        except SyncError:                                   # bad tracking_log.md headings: the card is made, link it
            try:
                card = notes.find_project(projects_folder, folder.name)
                link_card(card, folder)
                mark_older_than_log(card, folder)
            except OSError:
                continue
        except (OSError, ValueError):
            continue
        added.append(folder.name)
    return added


def mark_older_than_log(card, work_folder):
    """Make note.md look older than tracking_log.md, so the Stop hook tries to sync and says what to fix."""
    log_time = (Path(work_folder) / TRACKING_LOG).stat().st_mtime_ns
    one_second = 1_000_000_000
    os.utime(Path(card) / notes.NOTE_FILE, ns=(log_time - one_second, log_time - one_second))


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
    if not projects_folder or not Path(projects_folder).is_dir():
        return fail(f"settings.ini projects_folder= is {'empty' if not projects_folder else 'not a folder: ' + projects_folder}. "
                    "Set it to your dashboard projects folder, then try again.")
    work = Path(work_jira) / args.name
    if not notes.plain_name(args.name) or not work.is_dir():
        return fail(f"No folder {args.name} in {work_jira}. Use the project folder's exact name.")
    if not is_project_folder(work):
        return fail(f"{args.name} is not a project folder (names starting with _ or . are skipped). "
                    "Use a project folder's name.")

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
        return fail(f"Could not update the card ({err.strerror or err}). Is note.md open in another program? "
                    "Close it and try again.")
    return 0


def fail(message):
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")    # Windows pipes default to an old code page
    sys.exit(main(sys.argv[1:]))
