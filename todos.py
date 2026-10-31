"""The To do page's list: todos.md in the projects folder. Pure Python, no Flask.

The page owns the file and rewrites it whole after every change:

    # To do (edited by the Work Assistant To do page)

    - [ ] (high) call the vendor back
    - [ ] tidy the test folder
    - [x] send the weekly report

File order = the order the todos were added. Near-miss lines typed by hand (`* [ ] x`, `-[ ] x`,
`- [ ]x`, `- [] x`) count as todos and are written back in the form above; any other line is dropped
on the next save. Each change names a todo by its row (its place in the file, 0 = first) AND its text;
if they no longer match (the list was changed in another browser tab), nothing is saved and ListChanged
is raised. Every change returns the list it saved.
"""
import re
import threading
from pathlib import Path

TODO_FILE = "todos.md"
HEADER = "# To do (edited by the Work Assistant To do page)"
# No "reload the page": on a 409 the page reads the list again by itself.
CHANGED = ("The list changed in another tab or window, so nothing was saved. "
           "The fresh list is below: check it and try again.")
EMPTY = "Type something, or use × to delete it."
MAX_LENGTH = 500        # same as maxlength= on the page's text boxes
TOO_LONG = f"A todo can be at most {MAX_LENGTH} characters. Shorten it, and keep the details in a project note."
NOT_UTF8 = (f"{TODO_FILE} isn't saved as UTF-8. Open it in Notepad, choose File > Save As, set Encoding to UTF-8, "
            "save, then reload this page (F5).")
NO_FOLDER = "Can't find your projects folder ({}). Check projects_folder= in settings.ini, then restart the app."
NOT_A_FILE = f"There is a folder called {TODO_FILE} in your projects folder. Rename it, then reload this page (F5)."
HIGH_PREFIX = 'Don\'t start a todo with "(high)". Use the flag button to make it high.'
HIGH = "(high)"
LINE = re.compile(r"[-*+]\s*\[([ xX]?)\]\s*(.*)")     # - [ ] text   /   - [x] text   (+ near misses, see top)

# Flask answers each click on its own thread. Every read-change-write holds this lock, so two clicks at the
# same moment can't both read the old list and the second save wipe out the first. RLock: a change reads
# the file while already holding it.
_lock = threading.RLock()


class ListChanged(Exception):
    """The row + text sent by the page no longer match the file."""


class Unreadable(Exception):
    """todos.md can't be read (NO_FOLDER / NOT_A_FILE / NOT_UTF8 message)."""


class BadText(ValueError):
    """The typed text can't be saved (EMPTY / TOO_LONG / HIGH_PREFIX message)."""


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
            todos.append({"text": words, "high": high, "done": match.group(1) in ("x", "X")})
    return todos


def format_todos(todos):
    """List of todo dicts -> the full todos.md text (HEADER, a blank line, one line per todo, final newline)."""
    lines = [f"- [{'x' if t['done'] else ' '}] {HIGH + ' ' if t['high'] else ''}{t['text']}\n" for t in todos]
    return HEADER + "\n\n" + "".join(lines)


def clean_text(text):
    """The typed text on one line, trimmed. BadText (EMPTY / TOO_LONG / HIGH_PREFIX message) if it can't be saved.

    Line breaks become one space. "Line break" = anything splitlines() splits on (parse reads the file with
    it), which includes hidden characters Word/Excel can paste, not just Enter. A broken character (half an
    emoji from a bad paste) can't be saved as UTF-8, so it becomes "?".
    """
    text = text.encode("utf-8", "replace").decode("utf-8")
    text = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if not text:
        raise BadText(EMPTY)
    if len(text) > MAX_LENGTH:
        raise BadText(TOO_LONG)
    if text.lower().startswith(HIGH):
        raise BadText(HIGH_PREFIX)
    return text


def read_todos(projects_folder):
    """The todos in projects_folder/todos.md, file order. No file yet = []. Unreadable if it's not UTF-8 text."""
    path = Path(projects_folder) / TODO_FILE
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
    with _lock:
        todos = read_todos(projects_folder)
        todos.append({"text": text, "high": False, "done": False})
        return _write(projects_folder, todos)


def set_done(projects_folder, row, text, done):
    """Tick (done=True) or untick (done=False) one todo. Keeps its priority."""
    return _change(projects_folder, row, text, lambda t: t.update(done=bool(done)))


def set_high(projects_folder, row, text, high):
    """Make one todo high (True) or normal (False)."""
    return _change(projects_folder, row, text, lambda t: t.update(high=bool(high)))


def set_text(projects_folder, row, text, new_text):
    """Change one todo's words. new_text goes through clean_text."""
    new_text = clean_text(new_text)
    return _change(projects_folder, row, text, lambda t: t.update(text=new_text))


def delete(projects_folder, row, text):
    """Remove one todo for good."""
    return _change(projects_folder, row, text, None)


def clear_done(projects_folder, shown):
    """Remove every done todo for good. shown = the done todos' texts the page asked about, in file order:
    if the file's done todos differ (ticked or unticked in another tab), nothing is removed (ListChanged).
    """
    with _lock:
        todos = read_todos(projects_folder)
        if [t["text"] for t in todos if t["done"]] != shown:
            raise ListChanged(CHANGED)
        kept = [t for t in todos if not t["done"]]
        return _write(projects_folder, kept) if len(kept) < len(todos) else todos     # nothing done = no write


def _write(projects_folder, todos):
    """Save the whole list; returns it. Encodes first: write_text would empty the file before a failed encode."""
    data = format_todos(todos).encode("utf-8")
    (Path(projects_folder) / TODO_FILE).write_bytes(data)
    return todos


def _change(projects_folder, row, text, fn):
    """Find the todo at row, check it still has this text, apply fn to it (None = delete it), save."""
    with _lock:
        todos = read_todos(projects_folder)
        # app.py already refuses a row that isn't an int (its "page sent something odd" message); this check
        # keeps todos.py safe on its own. type(), not isinstance(): True is an int in Python.
        if not (type(row) is int and 0 <= row < len(todos) and todos[row]["text"] == text):
            raise ListChanged(CHANGED)
        if fn is None:
            del todos[row]
        else:
            fn(todos[row])
        return _write(projects_folder, todos)
