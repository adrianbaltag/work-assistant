"""Messages from the dashboard to Claude: Note, Blocker, Unblock. Pure Python, no Flask.

Each message is one small file in the project's work folder:

    <work folder>/.claude/dashboard-inbox/20261118-093000-000000-1a2b3c4d.json
    {"id": "1a2b3c4d", "kind": "note", "text": "...", "sent": "2026-11-18 09:30:00",
     "seen": "", "log_stamp": "", "reminded": false}

Who writes what (so two programs never fight over one file):
- the app only ADDS files (add) and reads them;
- the Claude Code hooks only MARK them (mark_seen, mark_reminded).

"seen" = the day a hook handed the message to Claude. "log_stamp" = what tracking_log.md looked like at that
moment. The message is finished when tracking_log.md has changed since (Claude wrote it into the log).
That is one check on the file's time and size, never on its text.
"""
import json
import logging
import uuid
from pathlib import Path

import notes

log = logging.getLogger(__name__)

INBOX_DIR = Path(".claude") / "dashboard-inbox"
LOG_FILE = "tracking_log.md"            # the same file the dashboard sync reads (project_note.TRACKING_LOG)
KINDS = ("note", "blocker", "unblock")
NEEDS_TEXT = ("note", "blocker")        # an Unblock may be sent with no words
HIDE_FILE = ".gitignore"                # inside the inbox: git then ignores the whole inbox, this file too
HIDE_TEXT = "# Dashboard messages for Claude: never part of the ticket's git history.\n*\n"
WAITING = "waiting for Claude"
SEEN = "seen by Claude {}"


def inbox_folder(work):
    return Path(work) / INBOX_DIR


def add(work, kind, text, now):
    """The app: leave one new message for Claude and return it. ValueError = unknown kind, or no text.

    The text is put on one line, as it also becomes one History line and one line in Claude's context.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown kind of message: {kind!r}. Use one of: {', '.join(KINDS)}.")
    text = " ".join(str(text or "").split())
    if kind in NEEDS_TEXT and not text:
        raise ValueError("The message is empty. Type a few words first.")
    message = {"id": uuid.uuid4().hex[:8], "kind": kind, "text": text,
               "sent": now.strftime("%Y-%m-%d %H:%M:%S"), "seen": "", "log_stamp": "", "reminded": False}
    folder = inbox_folder(work)
    folder.mkdir(parents=True, exist_ok=True)
    hide = folder / HIDE_FILE
    if not hide.exists():
        notes.safe_write(hide, HIDE_TEXT)
    # the time comes first in the name, down to the microsecond: sorted by name = oldest first
    notes.safe_write(folder / f"{now.strftime('%Y%m%d-%H%M%S-%f')}-{message['id']}.json", json.dumps(message))
    return message


def read_all(work):
    """Every message in the work folder, oldest first. No inbox = []. A broken file is skipped and logged."""
    return [message for _, message in read_files(work)]


def read_files(work):
    """[(file, message)], oldest first. Only files that hold a real message."""
    folder = inbox_folder(work)
    if not folder.is_dir():
        return []
    found = []
    for file in sorted(folder.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            notes.log_once(str(file), f"dashboard message {file.name} can't be read, skipped ({err})")
            continue
        if not isinstance(data, dict) or data.get("kind") not in KINDS or not data.get("id"):
            notes.log_once(str(file), f"dashboard message {file.name} is not a message, skipped")
            continue
        found.append((file, {"id": str(data["id"]), "kind": data["kind"], "text": str(data.get("text") or ""),
                             "sent": str(data.get("sent") or ""), "seen": str(data.get("seen") or ""),
                             "log_stamp": str(data.get("log_stamp") or ""), "reminded": data.get("reminded") is True}))
    return found


def log_stamp(work):
    """What tracking_log.md looks like now (time and size, as text). "" = there is no log, or it can't be read."""
    try:
        return notes.file_stamp(Path(work) / LOG_FILE)
    except OSError:
        return ""


def unseen(messages):
    """Messages no hook has handed to Claude yet."""
    return [m for m in messages if not m["seen"]]


def not_written(messages, stamp):
    """Messages Claude got, but tracking_log.md has not changed since: Claude has not written them down yet.

    stamp = log_stamp(work) now.
    """
    return [m for m in messages if m["seen"] and m["log_stamp"] == stamp]


def active_blocker(messages):
    """The user's blocker that is on now: the newest Blocker with no Unblock after it. None = not blocked.

    messages = oldest first, as read_all gives them.
    """
    for message in reversed(messages):
        if message["kind"] == "unblock":
            return None
        if message["kind"] == "blocker":
            return message
    return None


def status_text(message):
    """What the page shows next to a message: "waiting for Claude" or "seen by Claude 2026-11-18"."""
    return SEEN.format(message["seen"]) if message["seen"] else WAITING


def mark_seen(work, message_ids, now):
    """The hooks: these messages were just handed to Claude. Notes the day and what the log looks like now.

    Handed over again later = marked again: a fresh log stamp, and the Stop reminder may speak once more.
    """
    change(work, message_ids, {"seen": now.strftime("%Y-%m-%d"), "log_stamp": log_stamp(work), "reminded": False})


def mark_reminded(work, message_ids):
    """The hooks: the Stop hook reminded Claude about these once. It does not ask again until a new handover."""
    change(work, message_ids, {"reminded": True})


def change(work, message_ids, values):
    """Set values in the named messages. A file that can't be saved is logged and left as it was."""
    wanted = set(message_ids)
    for file, message in read_files(work):
        if message["id"] not in wanted:
            continue
        try:
            notes.safe_write(file, json.dumps({**message, **values}))
        except OSError as err:
            log.warning("dashboard message %s could not be marked (%s): Claude may be told about it again", file.name, err)
