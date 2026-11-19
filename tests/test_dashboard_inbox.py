"""dashboard_inbox.py: the small message files the dashboard leaves for Claude in a work folder.

The app only adds messages. The hooks only mark them (seen, reminded). All on made-up folders.
"""
import json
import os
import subprocess
from datetime import datetime, timedelta

import pytest

import dashboard_inbox as inbox
import project_note as pn

NOW = datetime(2026, 11, 18, 9, 30, 0)


def write_log(work, text="## Now working on\nM1\n"):
    (work / inbox.LOG_FILE).write_text(text, encoding="utf-8")


def change_log(work):
    """The log gets a new entry: a different size, and a later time."""
    file = work / inbox.LOG_FILE
    file.write_text(file.read_text(encoding="utf-8") + "one more line\n", encoding="utf-8")
    later = file.stat().st_mtime + 5
    os.utime(file, (later, later))


# ---------- add (the app) ----------

def test_add_makes_one_file_per_message(tmp_path):
    first = inbox.add(tmp_path, "note", "Dana wants the csv by Friday", NOW)
    second = inbox.add(tmp_path, "blocker", "Waiting for the lab key", NOW + timedelta(seconds=1))

    files = sorted((tmp_path / ".claude" / "dashboard-inbox").glob("*.json"))
    assert len(files) == 2
    assert first["id"] != second["id"]
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved == {"id": first["id"], "kind": "note", "text": "Dana wants the csv by Friday",
                     "sent": "2026-11-18 09:30:00", "seen": "", "log_stamp": "", "reminded": False}


def test_add_keeps_the_text_on_one_line(tmp_path):
    message = inbox.add(tmp_path, "note", "  first line\n\nsecond   line  ", NOW)
    assert message["text"] == "first line second line"


def test_add_refuses_an_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        inbox.add(tmp_path, "shout", "hello", NOW)
    assert inbox.read_all(tmp_path) == []


@pytest.mark.parametrize("kind", ["note", "blocker"])
def test_a_note_and_a_blocker_need_text(tmp_path, kind):
    with pytest.raises(ValueError):
        inbox.add(tmp_path, kind, "   ", NOW)


def test_unblock_needs_no_text(tmp_path):
    assert inbox.add(tmp_path, "unblock", "", NOW)["text"] == ""


def test_add_leaves_no_temp_file_behind(tmp_path):
    inbox.add(tmp_path, "note", "hello", NOW)
    names = [f.name for f in (tmp_path / ".claude" / "dashboard-inbox").iterdir() if f.name != ".gitignore"]
    assert len(names) == 1 and names[0].endswith(".json")


def test_git_never_sees_the_inbox(tmp_path):
    """An older ticket folder may not ignore .claude/: the inbox hides itself, so git status stays clean."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    inbox.add(tmp_path, "note", "hello", NOW)

    status = subprocess.run(["git", "-C", str(tmp_path), "status", "--porcelain"],
                            check=True, capture_output=True, text=True).stdout

    assert status == ""


def test_the_hide_file_is_written_once_and_is_no_message(tmp_path):
    inbox.add(tmp_path, "note", "first", NOW)
    hide = tmp_path / ".claude" / "dashboard-inbox" / ".gitignore"
    hide.write_text("*\n# kept\n", encoding="utf-8")

    inbox.add(tmp_path, "note", "second", NOW + timedelta(seconds=1))

    assert hide.read_text(encoding="utf-8") == "*\n# kept\n"
    assert [m["text"] for m in inbox.read_all(tmp_path)] == ["first", "second"]


# ---------- read_all ----------

def test_read_all_without_an_inbox_is_empty(tmp_path):
    assert inbox.read_all(tmp_path) == []


def test_read_all_is_oldest_first(tmp_path):
    inbox.add(tmp_path, "note", "third", NOW + timedelta(minutes=2))
    inbox.add(tmp_path, "note", "first", NOW)
    inbox.add(tmp_path, "note", "second", NOW + timedelta(microseconds=5))
    assert [m["text"] for m in inbox.read_all(tmp_path)] == ["first", "second", "third"]


def test_read_all_skips_a_broken_file_and_logs_it(tmp_path, caplog):
    inbox.add(tmp_path, "note", "good one", NOW)
    folder = tmp_path / ".claude" / "dashboard-inbox"
    (folder / "20261118-093001-000000-bad.json").write_text("{not json", encoding="utf-8")
    (folder / "20261118-093002-000000-odd.json").write_text('{"kind": "shout"}', encoding="utf-8")
    (folder / "20261118-093003-000000-list.json").write_text("[1, 2]", encoding="utf-8")

    with caplog.at_level("WARNING"):
        messages = inbox.read_all(tmp_path)

    assert [m["text"] for m in messages] == ["good one"]
    assert "20261118-093001-000000-bad.json" in caplog.text


# ---------- the log stamp ----------

def test_the_log_file_name_is_the_one_the_sync_reads():
    assert inbox.LOG_FILE == pn.TRACKING_LOG


def test_log_stamp_is_empty_without_a_log(tmp_path):
    assert inbox.log_stamp(tmp_path) == ""


def test_log_stamp_changes_when_the_log_changes(tmp_path):
    write_log(tmp_path)
    before = inbox.log_stamp(tmp_path)
    assert before
    change_log(tmp_path)
    assert inbox.log_stamp(tmp_path) != before


# ---------- mark_seen and what is still open (the hooks) ----------

def test_a_new_message_is_unseen_and_waiting(tmp_path):
    write_log(tmp_path)
    message = inbox.add(tmp_path, "note", "hello", NOW)

    messages = inbox.read_all(tmp_path)
    assert inbox.unseen(messages) == messages
    assert inbox.not_written(messages, inbox.log_stamp(tmp_path)) == []
    assert inbox.status_text(message) == "waiting for Claude"


def test_mark_seen_writes_the_date_and_the_log_stamp(tmp_path):
    write_log(tmp_path)
    message = inbox.add(tmp_path, "note", "hello", NOW)

    inbox.mark_seen(tmp_path, [message["id"]], NOW + timedelta(days=1))

    seen = inbox.read_all(tmp_path)[0]
    assert seen["seen"] == "2026-11-19"
    assert seen["log_stamp"] == inbox.log_stamp(tmp_path)
    assert seen["text"] == "hello" and seen["sent"] == message["sent"]
    assert inbox.unseen([seen]) == []
    assert inbox.status_text(seen) == "seen by Claude 2026-11-19"


def test_mark_seen_touches_only_the_named_messages(tmp_path):
    first = inbox.add(tmp_path, "note", "first", NOW)
    inbox.add(tmp_path, "note", "second", NOW + timedelta(seconds=1))

    inbox.mark_seen(tmp_path, [first["id"]], NOW)

    assert [m["seen"] for m in inbox.read_all(tmp_path)] == ["2026-11-18", ""]


def test_seen_but_log_unchanged_is_not_written_yet(tmp_path):
    write_log(tmp_path)
    message = inbox.add(tmp_path, "note", "hello", NOW)
    inbox.mark_seen(tmp_path, [message["id"]], NOW)

    messages = inbox.read_all(tmp_path)
    assert inbox.not_written(messages, inbox.log_stamp(tmp_path)) == messages


def test_seen_and_log_changed_is_done(tmp_path):
    write_log(tmp_path)
    message = inbox.add(tmp_path, "note", "hello", NOW)
    inbox.mark_seen(tmp_path, [message["id"]], NOW)
    change_log(tmp_path)

    messages = inbox.read_all(tmp_path)
    assert inbox.not_written(messages, inbox.log_stamp(tmp_path)) == []
    assert inbox.unseen(messages) == []


def test_a_log_made_after_the_handover_counts_as_changed(tmp_path):
    message = inbox.add(tmp_path, "note", "hello", NOW)
    inbox.mark_seen(tmp_path, [message["id"]], NOW)          # no tracking_log.md yet: the stamp is ""
    assert inbox.not_written(inbox.read_all(tmp_path), inbox.log_stamp(tmp_path)) != []

    write_log(tmp_path)

    assert inbox.not_written(inbox.read_all(tmp_path), inbox.log_stamp(tmp_path)) == []


def test_mark_reminded_is_kept_until_the_next_handover(tmp_path):
    write_log(tmp_path)
    message = inbox.add(tmp_path, "note", "hello", NOW)
    inbox.mark_seen(tmp_path, [message["id"]], NOW)

    inbox.mark_reminded(tmp_path, [message["id"]])
    assert inbox.read_all(tmp_path)[0]["reminded"] is True

    inbox.mark_seen(tmp_path, [message["id"]], NOW + timedelta(days=1))      # handed over again
    again = inbox.read_all(tmp_path)[0]
    assert again["reminded"] is False and again["seen"] == "2026-11-19"


def test_marking_a_message_that_is_gone_does_nothing(tmp_path):
    inbox.mark_seen(tmp_path, ["nope"], NOW)
    inbox.mark_reminded(tmp_path, ["nope"])
    assert inbox.read_all(tmp_path) == []


# ---------- the user's blocker ----------

def test_no_blocker_without_a_blocker_message(tmp_path):
    inbox.add(tmp_path, "note", "hello", NOW)
    assert inbox.active_blocker(inbox.read_all(tmp_path)) is None


def test_the_newest_blocker_is_the_active_one(tmp_path):
    inbox.add(tmp_path, "blocker", "old reason", NOW)
    inbox.add(tmp_path, "note", "hello", NOW + timedelta(seconds=1))
    inbox.add(tmp_path, "blocker", "new reason", NOW + timedelta(seconds=2))
    assert inbox.active_blocker(inbox.read_all(tmp_path))["text"] == "new reason"


def test_an_unblock_after_the_blocker_clears_it(tmp_path):
    inbox.add(tmp_path, "blocker", "waiting for the key", NOW)
    inbox.add(tmp_path, "unblock", "", NOW + timedelta(seconds=1))
    assert inbox.active_blocker(inbox.read_all(tmp_path)) is None


def test_a_blocker_after_an_unblock_is_active_again(tmp_path):
    inbox.add(tmp_path, "blocker", "first", NOW)
    inbox.add(tmp_path, "unblock", "", NOW + timedelta(seconds=1))
    inbox.add(tmp_path, "blocker", "second", NOW + timedelta(seconds=2))
    assert inbox.active_blocker(inbox.read_all(tmp_path))["text"] == "second"


def test_a_seen_blocker_stays_active(tmp_path):
    message = inbox.add(tmp_path, "blocker", "waiting for the key", NOW)
    inbox.mark_seen(tmp_path, [message["id"]], NOW)
    assert inbox.active_blocker(inbox.read_all(tmp_path))["id"] == message["id"]
