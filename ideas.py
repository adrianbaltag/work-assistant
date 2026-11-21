"""The Ideas page's list: ideas.md in the projects folder. Pure Python, no Flask.

The page owns the file and rewrites it whole after every change. Newest idea first:

    # Ideas (edited by the Work Assistant Ideas page)

    ## 2026-11-21 · Rename old scripts
    They all start with tmp_.
    Pick one style.

    ## 2026-11-20 · A quick one

One idea = a "## date · name" line, then its details (any number of lines, may be none).
The name is the first line you typed; the details are the rest. There is no edit: to change an idea,
delete it and add it again. Text above the first "## " line is dropped on the next save.
Each change names an idea by its row (its place in the file, 0 = first = newest) AND its name;
if they no longer match (changed in another browser tab), nothing is saved and ListChanged is raised.
"""
import re
import threading
from pathlib import Path

IDEA_FILE = "ideas.md"
HEADER = "# Ideas (edited by the Work Assistant Ideas page)"
MAX_LENGTH = 2000       # same as maxlength= on the page's box
NO_NAME = "(no name)"   # a "## " line typed by hand with only a date on it
# No "reload the page": on a 409 the page reads the list again by itself.
CHANGED = ("The list changed in another tab or window, so nothing was saved. "
           "The fresh list is below: check it and try again.")
STALE_IDEA = ("This idea changed in another tab or window, so no project was made. "
              "Close this form and look at the fresh Ideas list.")
EMPTY = "Type an idea first."
TOO_LONG = (f"An idea can be at most {MAX_LENGTH} characters. Shorten it, "
            "or start it as a project and keep the details in the project's note.")
NOT_UTF8 = (f"{IDEA_FILE} isn't saved as UTF-8. Open it in Notepad, choose File > Save As, set Encoding to UTF-8, "
            "save, then reload this page (F5).")
NO_FOLDER = "Can't find your projects folder ({}). Check projects_folder= in settings.ini, then restart the app."
NOT_A_FILE = f"There is a folder called {IDEA_FILE} in your projects folder. Rename it, then reload this page (F5)."

HEADING = re.compile(r"## (\d{4}-\d{2}-\d{2}) ·(.*)")    # ## 2026-11-21 · name

# Flask answers each click on its own thread. Every read-change-write holds this lock, so two clicks at the
# same moment can't both read the old list and the second save wipe out the first. RLock: a change reads
# the file while already holding it.
_lock = threading.RLock()


class ListChanged(Exception):
    """The row + name sent by the page no longer match the file."""


class Unreadable(Exception):
    """ideas.md can't be read (NO_FOLDER / NOT_A_FILE / NOT_UTF8 message)."""


class BadText(ValueError):
    """The typed text can't be saved (EMPTY / TOO_LONG message)."""


# Each idea is a dict: {"date": "2026-11-21" or "", "name": str, "details": str (lines joined by \n, may be "")}


def _tidy(lines):
    """Strip each line, drop blank lines at both ends, keep at most one blank line in a row. Returns the text."""
    kept = []
    for line in (part.strip() for part in lines):
        if line or (kept and kept[-1]):
            kept.append(line)
    while kept and not kept[-1]:
        kept.pop()
    return "\n".join(kept)


def parse(text):
    """ideas.md text -> list of idea dicts, in file order (newest first)."""
    found = []
    current = None
    for line in text.splitlines():
        if line.startswith("## "):         # only a line that STARTS with "## ": a details line never does (see format)
            match = HEADING.fullmatch(line.strip())
            date, name = (match.group(1), match.group(2)) if match else ("", line[3:])
            current = {"date": date, "name": name.strip(), "lines": []}
            found.append(current)
        elif current is not None:
            current["lines"].append(line)
    ideas = []
    for idea in found:
        details = _tidy(idea["lines"])
        if idea["name"] or details:         # an empty "## " line with nothing under it is dropped
            ideas.append({"date": idea["date"], "name": idea["name"] or NO_NAME, "details": details})
    return ideas


def format_ideas(ideas):
    """List of idea dicts -> the full ideas.md text (HEADER, then each idea after a blank line, final newline).

    Details lines are stripped, so none starts with "## ": a pasted "## x" line is written as " ## x"
    and so stays inside its idea (parse strips it back to "## x").
    """
    blocks = []
    for idea in ideas:
        lines = [f"## {idea['date']} · {idea['name']}" if idea["date"] else f"## {idea['name']}"]
        lines += [" " + line if line.startswith("#") else line for line in idea["details"].split("\n") if idea["details"]]
        blocks.append("\n".join(lines) + "\n")
    return HEADER + "\n" + "".join("\n" + block for block in blocks)


def clean(text):
    """The typed text -> (name, details). BadText (EMPTY / TOO_LONG message) if it can't be saved.

    Name = the first line with words on it. Details = the rest, tidied the same way parse reads them, so what
    is saved reads back the same. A broken character (half an emoji from a bad paste) can't be saved as
    UTF-8, so it becomes "?".
    """
    text = text.encode("utf-8", "replace").decode("utf-8")
    tidy = _tidy(text.splitlines())
    if not tidy:
        raise BadText(EMPTY)
    if len(tidy) > MAX_LENGTH:
        raise BadText(TOO_LONG)
    name, _, details = tidy.partition("\n")
    return name, details.strip("\n")


def read_ideas(projects_folder):
    """The ideas in projects_folder/ideas.md, file order. No file yet = []. Unreadable if it can't be read as text."""
    path = Path(projects_folder) / IDEA_FILE
    if not path.parent.is_dir():
        raise Unreadable(NO_FOLDER.format(path.parent))
    if path.is_dir():
        raise Unreadable(NOT_A_FILE)
    if not path.is_file():
        return []
    with _lock:
        try:
            return parse(path.read_text(encoding="utf-8-sig"))
        except UnicodeDecodeError:
            raise Unreadable(NOT_UTF8) from None


def listing(ideas):
    """What the page gets: {"ideas": [... each with its "row" (place in the file) added], "count": n}."""
    return {"ideas": [dict(idea, row=i) for i, idea in enumerate(ideas)], "count": len(ideas)}


def add(projects_folder, text, today):
    """Add an idea at the top of the file (creates ideas.md on the first add). today = "YYYY-MM-DD"."""
    name, details = clean(text)
    with _lock:
        ideas = read_ideas(projects_folder)
        ideas.insert(0, {"date": today, "name": name, "details": details})
        return _write(projects_folder, ideas)


def get(projects_folder, row, name):
    """The idea at row, if it still has this name. ListChanged if not."""
    with _lock:
        ideas = read_ideas(projects_folder)
        _check(ideas, row, name)
        return ideas[row]


def delete(projects_folder, row, name):
    """Remove one idea for good. Returns the list it saved."""
    with _lock:
        ideas = read_ideas(projects_folder)
        _check(ideas, row, name)
        del ideas[row]
        return _write(projects_folder, ideas)


def _check(ideas, row, name):
    # app.py already refuses a row that isn't an int; this check keeps ideas.py safe on its own.
    # type(), not isinstance(): True is an int in Python.
    if not (type(row) is int and 0 <= row < len(ideas) and ideas[row]["name"] == name):
        raise ListChanged(CHANGED)


def _write(projects_folder, ideas):
    """Save the whole list; returns it. Encodes first: write_text would empty the file before a failed encode."""
    data = format_ideas(ideas).encode("utf-8")
    (Path(projects_folder) / IDEA_FILE).write_bytes(data)
    return ideas
