"""Read project notes from the projects folder. Pure Python, no Flask.

Each project is a folder (named after its ticket ID) holding a note.md:

    ---
    title: Fix the RAN alarms
    status: pending
    ---
    # Notes ...
"""
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

NOTE_FILE = "note.md"
ARCHIVE_FOLDER = "_archive"     # archived projects, inside the projects folder
FILE_ARCHIVE = "archive"        # archived files, inside one project folder
DEFAULTS = {"status": "active", "priority": "normal"}
QUIET_DAYS = 7               # untouched this long = "gone quiet"
HISTORY_HEADING = "## History"
HISTORY_LINE = re.compile(r"(\d{4}-\d{2}-\d{2}) · (.+?) · (.*)")    # 2026-10-14 · you · text
FILE_DIRS = ("sessions", "raw")    # the only sub-folders the card shows and edits
UPLOAD_DIR = "raw"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
TEXT_LIMIT = 1_000_000          # bigger text files are not opened in the editor (the page would hang)


def parse_note(text):
    """Split note text into (fields dict, body text).

    Fields are simple "key: value" lines between two "---" lines.
    Unknown keys are kept. No "---" at the top means no fields.
    """
    lines = text.splitlines(keepends=True)
    end = block_end(lines)
    if end is None:
        return {}, text     # no block, or no closing "---": treat it all as body

    fields = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields, "".join(lines[end + 1:])


def block_end(lines):
    """Line number of the closing "---" of the fields block, or None if there is no block."""
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return i
    return None


def has_fields_block(text):
    """True if the note starts with a complete "---" fields block."""
    return block_end(text.splitlines()) is not None


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


# ---------- editing note.md (slice 3) ----------

class StaleNote(Exception):
    """A file changed on disk after the card opened it (e.g. Claude Code saved it)."""


def set_fields(text, changes):
    """Return the note text with these fields set. Body, order and other keys stay as they are.

    Existing keys are changed in place. New keys go at the end of the block,
    but only if they have a value. A note without a block gets one.
    """
    changes = {k: " ".join(str(v).split("\n")).strip() for k, v in changes.items()}
    lines = text.splitlines(keepends=True)
    end = block_end(lines)
    if end is None:
        lines, end = ["---\n", "---\n"] + lines, 1

    seen = set()
    for i in range(1, end):
        key = lines[i].partition(":")[0].strip()
        if key in changes:         # every copy, because parse_note reads the last one
            value = changes[key]
            lines[i] = f"{key}: {value}\n" if value else f"{key}:\n"
            seen.add(key)
    new = [f"{k}: {v}\n" for k, v in changes.items() if v and k not in seen]
    return "".join(lines[:end] + new + lines[end:])


def history_lines(lines):
    """Positions (start, end) of the list lines under "## History", or None if no such section."""
    for i, line in enumerate(lines):
        if line.strip() == HISTORY_HEADING:
            end = i + 1
            while end < len(lines) and not lines[end].startswith(("# ", "## ")):
                end += 1
            return i + 1, end
    return None


def read_history(text):
    """The "- date · who · text" lines under "## History", as dicts, in file order (newest first)."""
    lines = text.splitlines()
    found = history_lines(lines)
    if not found:
        return []
    history = []
    for line in lines[found[0]:found[1]]:
        if line.startswith("- "):
            match = HISTORY_LINE.fullmatch(line[2:].strip())
            date, who, said = match.groups() if match else ("", "", line[2:].strip())
            history.append({"date": date, "who": who, "text": said})
    return history


def add_history(text, said, date, who="you"):
    """Return the note text with a new history line on top (section is created if missing)."""
    entry = f"- {date} · {who} · {' '.join(said.split())}\n"
    lines = text.splitlines(keepends=True)
    found = history_lines(lines)
    if not found:
        return text.rstrip("\n") + f"\n\n{HISTORY_HEADING}\n{entry}"
    return "".join(lines[:found[0]] + [entry] + lines[found[0]:])


# ---------- finding and saving a project safely ----------

def find_project(projects_folder, project_id):
    """The folder of this project, or None if the ID is not a plain, open project.

    Stops IDs like "../x" from reaching files outside the projects folder.
    """
    if (not project_id or project_id != Path(project_id).name
            or project_id.startswith(".") or project_id == ARCHIVE_FOLDER):
        return None
    folder = Path(projects_folder) / project_id
    return folder if (folder / NOTE_FILE).is_file() else None


def file_stamp(path):
    """A file's last-changed time and size, as text. If it differs later, someone else saved the file.

    Size too, because some disks round the time to 1-2 seconds.
    """
    info = Path(path).stat()
    return f"{info.st_mtime_ns}-{info.st_size}"


def note_stamp(folder):
    return file_stamp(Path(folder) / NOTE_FILE)


def free_name(target_dir, name, now):
    """The path for name in target_dir, with a time suffix if it is taken: "a (2026-10-15 10-42).txt"."""
    name = Path(name)
    target = Path(target_dir) / name
    suffix = now.strftime(" (%Y-%m-%d %H-%M)")
    count = 1
    while target.exists():
        extra = suffix if count == 1 else f"{suffix[:-1]} {count})"
        target = Path(target_dir) / f"{name.stem}{extra}{name.suffix}"
        count += 1
    return target


def archive_copy(path, folder, now):
    """Copy a file into the project's archive folder. Never overwrites: a taken name gets a time suffix."""
    target_dir = Path(folder) / FILE_ARCHIVE / Path(path).parent.relative_to(folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = free_name(target_dir, Path(path).name, now)
    shutil.copy2(path, target)
    return target


def write_note(folder, text, stamp, now, force=False):
    """Save note.md and return its new stamp.

    stamp = what the card saw when it opened. If the file changed since:
    raise StaleNote, or with force=True archive their version first, then save.
    """
    if not has_fields_block(text):
        raise ValueError("The note must start with the --- fields block.")
    return write_file(Path(folder) / NOTE_FILE, folder, text, stamp, now, force)


def write_file(path, folder, text, stamp, now, force=False):
    """Save any text file in the project, with the same "changed since you opened it?" check as note.md."""
    if file_stamp(path) != stamp:
        if not force:
            raise StaleNote()
        archive_copy(path, folder, now)
    Path(path).write_text(text, encoding="utf-8")
    return file_stamp(path)


# ---------- sessions\ and raw\ files (slice 4) ----------

def list_files(folder):
    """The files in sessions\\ and raw\\, newest name first (session files are named by date)."""
    files = {}
    for dir in FILE_DIRS:
        path = Path(folder) / dir
        found = path.iterdir() if path.is_dir() else []
        files[dir] = [{"name": f.name, "size": f.stat().st_size}
                      for f in sorted(found, key=lambda f: f.name, reverse=True)
                      if f.is_file() and not f.name.startswith(".")]
    return files


def file_path(folder, dir, name):
    """folder/dir/name, or None if dir is not sessions/raw or name is not a plain, visible file name.

    Like find_project: stops names like "../note.md" from reaching other files.
    """
    if dir not in FILE_DIRS or not name or name != Path(name).name or name.startswith("."):
        return None
    return Path(folder) / dir / name


def read_file(path):
    """What the card shows: {"kind": "text", "text": ...}, {"kind": "image"} or {"kind": "other"}.

    Text = any file that reads as UTF-8 and is not huge. Other = Excel, PDF, zip, ...
    """
    path = Path(path)
    if path.suffix.lower() in IMAGE_TYPES:
        return {"kind": "image"}
    if path.stat().st_size > TEXT_LIMIT:
        return {"kind": "other"}
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")      # -sig: drops the BOM Windows Notepad may add
    except UnicodeDecodeError:
        return {"kind": "other"}
    return {"kind": "other"} if "\0" in text else {"kind": "text", "text": text}


def new_file(folder, dir, name):
    """Create an empty file. Raises FileExistsError if the name is taken."""
    path = Path(folder) / dir / name
    path.parent.mkdir(exist_ok=True)
    path.touch(exist_ok=False)
    return path


def rename_file(path, new_name):
    """Rename within the same folder. Raises FileExistsError if the name is taken.

    A case-only change (a.txt -> A.txt) is allowed: on Windows that is the same file.
    """
    path = Path(path)
    target = path.with_name(new_name)
    if target.exists() and not target.samefile(path):
        raise FileExistsError(new_name)
    path.rename(target)
    return target


def archive_file(path, folder, now):
    """"Delete" = move the file to the project's archive folder. Nothing is ever really deleted."""
    target = archive_copy(path, folder, now)
    Path(path).unlink()
    return target


def save_upload(folder, name, data, now):
    """Save uploaded bytes in raw\\ and return the name used. A taken name gets a time suffix."""
    target_dir = Path(folder) / UPLOAD_DIR
    target_dir.mkdir(exist_ok=True)
    target = free_name(target_dir, name, now)
    target.write_bytes(data)
    return target.name
