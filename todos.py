"""The To do page's list: todos.md in the projects folder. Pure Python, no Flask.

The page owns the file and rewrites it whole after every change:

    # To do (edited by the Work Assistant To do page)

    - [ ] (high) call the vendor back
    - [ ] tidy the test folder
    - [x] send the weekly report

File order = the order the todos were added. Lines in any other format are dropped on the next save.
Each change names a todo by its row (its place in the file, 0 = first) AND its text; if they no longer
match (the list was changed in another browser tab), nothing is saved and ListChanged is raised.
"""
import re
from pathlib import Path

TODO_FILE = "todos.md"
HEADER = "# To do (edited by the Work Assistant To do page)"
CHANGED = "The list changed since you loaded it. Reload the page (F5) and try again."
EMPTY = "Type something, or use × to delete it."
ONE_LINE = "A todo is one line. Remove the line breaks."
HIGH_PREFIX = 'Don\'t start a todo with "(high)". Use the flag button to make it high.'
HIGH = "(high)"
LINE = re.compile(r"- \[([ xX])\]\s+(.*)")     # - [ ] text   /   - [x] text


class ListChanged(Exception):
    """The row + text sent by the page no longer match the file."""


# Each todo is a dict: {"text": str, "high": bool, "done": bool}


def parse(text):
    """todos.md text -> list of todo dicts, in file order. Lines that aren't todos are skipped."""
    todos = []
    for line in text.splitlines():
        match = LINE.fullmatch(line.strip())
        if not match:
            continue
        words = match.group(2).strip()
        high = words.lower().startswith(HIGH)
        if high:
            words = words[len(HIGH):].strip()
        if words:
            todos.append({"text": words, "high": high, "done": match.group(1) != " "})
    return todos


def format_todos(todos):
    """List of todo dicts -> the full todos.md text (HEADER, a blank line, one line per todo, final newline)."""
    lines = [f"- [{'x' if t['done'] else ' '}] {HIGH + ' ' if t['high'] else ''}{t['text']}\n" for t in todos]
    return HEADER + "\n\n" + "".join(lines)


def clean_text(text):
    """The typed text, trimmed. ValueError (EMPTY / ONE_LINE / HIGH_PREFIX message) if it can't be saved."""
    text = text.strip()
    if not text:
        raise ValueError(EMPTY)
    if "\n" in text or "\r" in text:
        raise ValueError(ONE_LINE)
    if text.lower().startswith(HIGH):
        raise ValueError(HIGH_PREFIX)
    return text


def read_todos(projects_folder):
    """The todos in projects_folder/todos.md, file order. No file yet = []."""
    path = Path(projects_folder) / TODO_FILE
    if not path.is_file():
        return []
    return parse(path.read_text(encoding="utf-8-sig"))


def listing(todos):
    """What the page gets: {"todos": [...], "open": n, "open_high": n, "done": n}.

    todos is in display order, each with its "row" (place in the file) added:
    open high (file order), then open normal (file order), then done (file order, any priority).
    """
    rows = [dict(t, row=i) for i, t in enumerate(todos)]
    open_high = [t for t in rows if not t["done"] and t["high"]]
    open_normal = [t for t in rows if not t["done"] and not t["high"]]
    done = [t for t in rows if t["done"]]
    return {"todos": open_high + open_normal + done,
            "open": len(open_high) + len(open_normal), "open_high": len(open_high), "done": len(done)}


def add(projects_folder, text):
    """Add a normal, open todo at the end of the file (creates todos.md on the first add)."""
    text = clean_text(text)
    todos = read_todos(projects_folder)
    todos.append({"text": text, "high": False, "done": False})
    _write(projects_folder, todos)


def set_done(projects_folder, row, text, done):
    """Tick (done=True) or untick (done=False) one todo. Keeps its priority."""
    _change(projects_folder, row, text, lambda t: t.update(done=bool(done)))


def set_high(projects_folder, row, text, high):
    """Make one todo high (True) or normal (False)."""
    _change(projects_folder, row, text, lambda t: t.update(high=bool(high)))


def set_text(projects_folder, row, text, new_text):
    """Change one todo's words. new_text goes through clean_text."""
    new_text = clean_text(new_text)
    _change(projects_folder, row, text, lambda t: t.update(text=new_text))


def delete(projects_folder, row, text):
    """Remove one todo for good."""
    _change(projects_folder, row, text, None)


def clear_done(projects_folder):
    """Remove every done todo for good. Returns how many were removed."""
    todos = read_todos(projects_folder)
    kept = [t for t in todos if not t["done"]]
    if len(kept) < len(todos):      # nothing done = no write
        _write(projects_folder, kept)
    return len(todos) - len(kept)


def _write(projects_folder, todos):
    (Path(projects_folder) / TODO_FILE).write_text(format_todos(todos), encoding="utf-8")


def _change(projects_folder, row, text, fn):
    """Find the todo at row, check it still has this text, apply fn to it (None = delete it), save."""
    todos = read_todos(projects_folder)
    if not (type(row) is int and 0 <= row < len(todos) and todos[row]["text"] == text):     # type(): True is an int
        raise ListChanged(CHANGED)
    if fn is None:
        del todos[row]
    else:
        fn(todos[row])
    _write(projects_folder, todos)
