"""Read project notes from the projects folder. Pure Python, no Flask.

Each project is a folder (named after its ticket ID) holding a note.md:

    ---
    title: Fix the RAN alarms
    status: pending
    ---
    # Notes ...
"""
import os
from datetime import datetime
from pathlib import Path

NOTE_FILE = "note.md"
ARCHIVE_FOLDER = "_archive"     # archived projects, inside the projects folder
FILE_ARCHIVE = "archive"        # archived files, inside one project folder
DEFAULTS = {"status": "active", "priority": "normal"}
QUIET_DAYS = 7               # untouched this long = "gone quiet"


def parse_note(text):
    """Split note text into (fields dict, body text).

    Fields are simple "key: value" lines between two "---" lines.
    Unknown keys are kept. No "---" at the top means no fields.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    fields = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fields, "".join(lines[i + 1:])
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return {}, text     # no closing "---": treat it all as body


def newest_change(folder):
    """Newest modified time of any file in the project, skipping its archive folder."""
    newest = 0
    for root, dirs, files in os.walk(folder):
        if Path(root) == Path(folder) and FILE_ARCHIVE in dirs:
            dirs.remove(FILE_ARCHIVE)
        for name in files:
            newest = max(newest, os.path.getmtime(os.path.join(root, name)))
    return newest


def read_project(folder):
    """Read one project folder into a dict: id, fields (with defaults), body, updated."""
    folder = Path(folder)
    text = (folder / NOTE_FILE).read_text(encoding="utf-8-sig")
    fields, body = parse_note(text)
    project = {**DEFAULTS, "title": folder.name, **fields}
    project.update(id=folder.name, body=body, updated=newest_change(folder))
    return project


def list_projects(projects_folder):
    """All projects in the projects folder, sorted by id.

    A project is a sub-folder with a note.md. Skips _archive and hidden folders.
    """
    projects = []
    for folder in sorted(Path(projects_folder).iterdir()):
        if (folder.is_dir()
                and folder.name != ARCHIVE_FOLDER
                and not folder.name.startswith(".")
                and (folder / NOTE_FILE).is_file()):
            projects.append(read_project(folder))
    return projects


def dashboard(projects, now):
    """Add days_ago and quiet to each project, sorted for the dashboard.

    Critical projects first, then the longest-untouched. Ideas never go quiet.
    """
    for p in projects:
        last = datetime.fromtimestamp(p["updated"]).date()
        p["days_ago"] = (now.date() - last).days
        p["quiet"] = p["status"] != "idea" and p["days_ago"] >= QUIET_DAYS
    return sorted(projects, key=lambda p: (p["priority"] != "critical", -p["days_ago"]))
