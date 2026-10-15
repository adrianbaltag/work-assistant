"""Slice 1: reading project notes and listing projects (notes.py, no Flask)."""
import os
from datetime import datetime, timedelta

import pytest

import notes

NOTE = """---
title: Fix the RAN alarms
status: pending
priority: high
next: call vendor at 10:30
blocked_by:
jira: DEMO-1111
owner: me
---
# Notes

Some text.
"""


def make_project(root, folder, text=NOTE):
    """Create root/folder/note.md and return the project folder."""
    path = root / folder
    path.mkdir()
    (path / "note.md").write_text(text, encoding="utf-8")
    return path


# ---------- parse_note: text -> (fields, body) ----------

def test_parse_note_splits_fields_and_body():
    fields, body = notes.parse_note(NOTE)
    assert fields["title"] == "Fix the RAN alarms"
    assert fields["status"] == "pending"
    assert body == "# Notes\n\nSome text.\n"


def test_parse_note_keeps_unknown_keys():
    fields, _ = notes.parse_note(NOTE)
    assert fields["owner"] == "me"


def test_parse_note_value_can_contain_a_colon():
    fields, _ = notes.parse_note(NOTE)
    assert fields["next"] == "call vendor at 10:30"


def test_parse_note_empty_value_is_empty_string():
    fields, _ = notes.parse_note(NOTE)
    assert fields["blocked_by"] == ""


def test_parse_note_without_frontmatter_is_all_body():
    fields, body = notes.parse_note("just text\n")
    assert fields == {}
    assert body == "just text\n"


# ---------- read_project: one project folder -> dict ----------

def test_read_project_has_id_fields_and_body(tmp_path):
    project = notes.read_project(make_project(tmp_path, "DEMO-1111"))
    assert project["id"] == "DEMO-1111"
    assert project["title"] == "Fix the RAN alarms"
    assert project["priority"] == "high"
    assert project["body"].startswith("# Notes")


def test_read_project_fills_defaults(tmp_path):
    project = notes.read_project(make_project(tmp_path, "my-idea", "no fields\n"))
    assert project["title"] == "my-idea"      # folder name
    assert project["status"] == "active"
    assert project["priority"] == "normal"


def test_read_project_updated_is_newest_file_ignoring_archive(tmp_path):
    folder = make_project(tmp_path, "DEMO-1111")
    (folder / "sessions").mkdir()
    session = folder / "sessions" / "2026-10-14.md"
    session.write_text("x")
    (folder / "archive").mkdir()
    archived = folder / "archive" / "old.md"
    archived.write_text("x")
    os.utime(folder / "note.md", (1000, 1000))
    os.utime(session, (2000, 2000))
    os.utime(archived, (9000, 9000))   # newest, but archive\ doesn't count

    assert notes.read_project(folder)["updated"] == 2000


# ---------- list_projects: projects folder -> list of dicts ----------

def test_list_projects_finds_each_project_sorted_by_id(tmp_path):
    make_project(tmp_path, "DEMO-2222")
    make_project(tmp_path, "DEMO-1111")
    ids = [p["id"] for p in notes.list_projects(tmp_path)]
    assert ids == ["DEMO-1111", "DEMO-2222"]


def test_list_projects_skips_archive_hidden_loose_files_and_no_note(tmp_path):
    make_project(tmp_path, "DEMO-1111")
    (tmp_path / "_archive").mkdir()
    make_project(tmp_path / "_archive", "DEMO-0001")
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "readme.txt").write_text("x")
    (tmp_path / "empty-folder").mkdir()          # no note.md = not a project
    ids = [p["id"] for p in notes.list_projects(tmp_path)]
    assert ids == ["DEMO-1111"]


# ---------- dashboard: projects + today -> sorted rows with days_ago, quiet ----------

NOW = datetime(2026, 10, 15, 12, 0)


def row(id, days, status="active", priority="normal"):
    """A project dict as list_projects returns it, last touched `days` ago."""
    updated = (NOW - timedelta(days=days)).timestamp()
    return {"id": id, "status": status, "priority": priority, "updated": updated}


def test_dashboard_counts_days_since_last_change():
    rows = notes.dashboard([row("A", 0), row("B", 3)], NOW)
    assert {r["id"]: r["days_ago"] for r in rows} == {"A": 0, "B": 3}


def test_dashboard_gone_quiet_after_7_days():
    rows = notes.dashboard([row("A", 6), row("B", 7)], NOW)
    assert {r["id"]: r["quiet"] for r in rows} == {"A": False, "B": True}


def test_dashboard_ideas_never_go_quiet():
    rows = notes.dashboard([row("A", 30, status="idea")], NOW)
    assert rows[0]["quiet"] is False


def test_dashboard_sorts_critical_first_then_longest_untouched():
    rows = notes.dashboard([
        row("new", 1),
        row("old", 9),
        row("crit-new", 0, priority="critical"),
        row("crit-old", 5, priority="critical"),
    ], NOW)
    assert [r["id"] for r in rows] == ["crit-old", "crit-new", "old", "new"]


# ---------- slice 3: editing note.md ----------

def test_set_fields_changes_values_in_place_and_keeps_the_rest():
    text = notes.set_fields(NOTE, {"next": "send report", "status": "active"})
    fields, body = notes.parse_note(text)
    assert fields["next"] == "send report"
    assert fields["status"] == "active"
    assert fields["owner"] == "me"                       # unknown key kept
    assert list(fields) == list(notes.parse_note(NOTE)[0])  # same order
    assert body == "# Notes\n\nSome text.\n"


def test_set_fields_adds_new_keys_but_not_new_empty_ones():
    text = notes.set_fields("---\ntitle: X\n---\nbody\n", {"jira": "DEMO-9", "folder": ""})
    assert text == "---\ntitle: X\njira: DEMO-9\n---\nbody\n"


def test_set_fields_empty_value_keeps_the_key():
    fields, _ = notes.parse_note(notes.set_fields(NOTE, {"jira": ""}))
    assert fields["jira"] == ""


def test_set_fields_turns_newlines_into_spaces():
    fields, _ = notes.parse_note(notes.set_fields(NOTE, {"next": "line one\nline two"}))
    assert fields["next"] == "line one line two"


def test_set_fields_creates_the_block_when_note_has_none():
    assert notes.set_fields("just text\n", {"title": "X"}) == "---\ntitle: X\n---\njust text\n"


def test_has_fields_block():
    assert notes.has_fields_block(NOTE)
    assert notes.has_fields_block("---\n---\n")
    assert not notes.has_fields_block("just text\n")
    assert not notes.has_fields_block("---\ntitle: X\nno closing line\n")


HISTORY_NOTE = """---
title: X
---
## Goal
Something.

## History
- 2026-10-14 · Claude Code · Wrote gap questions
- 2026-10-13 · you · Ticket assigned
"""


def test_read_history_reads_lines_newest_first():
    assert notes.read_history(HISTORY_NOTE) == [
        {"date": "2026-10-14", "who": "Claude Code", "text": "Wrote gap questions"},
        {"date": "2026-10-13", "who": "you", "text": "Ticket assigned"},
    ]


def test_read_history_stops_at_the_next_heading_and_keeps_odd_lines():
    text = "## History\n- typed by hand\n\n## Later\n- 2026-01-01 · you · not history\n"
    assert notes.read_history(text) == [{"date": "", "who": "", "text": "typed by hand"}]


def test_read_history_none_when_no_section():
    assert notes.read_history(NOTE) == []


def test_add_history_puts_the_new_line_first():
    text = notes.add_history(HISTORY_NOTE, "Senior said: Northeast only", "2026-10-15")
    assert notes.read_history(text)[0] == {"date": "2026-10-15", "who": "you",
                                           "text": "Senior said: Northeast only"}
    assert len(notes.read_history(text)) == 3


def test_add_history_creates_the_section_at_the_bottom():
    text = notes.add_history(NOTE, "first line", "2026-10-15")
    assert text.endswith("Some text.\n\n## History\n- 2026-10-15 · you · first line\n")


# ---------- slice 3: finding and saving a project safely ----------

def test_find_project_accepts_a_real_project_only(tmp_path):
    make_project(tmp_path, "DEMO-1111")
    make_project(tmp_path, ".hidden")
    (tmp_path / "_archive").mkdir()
    (tmp_path / "no-note").mkdir()
    assert notes.find_project(tmp_path, "DEMO-1111") == tmp_path / "DEMO-1111"
    for bad in ["../DEMO-1111", "DEMO-1111/sessions", ".hidden", "_archive", "no-note", "missing", ""]:
        assert notes.find_project(tmp_path, bad) is None, bad


def test_write_note_saves_when_nobody_else_changed_it(tmp_path):
    folder = make_project(tmp_path, "P")
    stamp = notes.note_stamp(folder)
    new_stamp = notes.write_note(folder, "---\ntitle: New\n---\n", stamp, NOW)
    assert (folder / "note.md").read_text(encoding="utf-8") == "---\ntitle: New\n---\n"
    assert new_stamp == notes.note_stamp(folder)


def changed_by_someone_else(folder):
    """Simulate Claude Code saving note.md after the card was opened."""
    note = folder / "note.md"
    note.write_text("---\ntitle: Theirs\n---\n", encoding="utf-8")
    os.utime(note, ns=(5_000_000_000, 5_000_000_000))


def test_write_note_refuses_when_the_file_changed_meanwhile(tmp_path):
    folder = make_project(tmp_path, "P")
    stamp = notes.note_stamp(folder)
    changed_by_someone_else(folder)
    with pytest.raises(notes.StaleNote):
        notes.write_note(folder, "---\ntitle: Mine\n---\n", stamp, NOW)
    assert "Theirs" in (folder / "note.md").read_text(encoding="utf-8")


def test_write_note_force_archives_their_version_first(tmp_path):
    folder = make_project(tmp_path, "P")
    stamp = notes.note_stamp(folder)
    changed_by_someone_else(folder)
    notes.write_note(folder, "---\ntitle: Mine\n---\n", stamp, NOW, force=True)
    assert "Mine" in (folder / "note.md").read_text(encoding="utf-8")
    assert "Theirs" in (folder / "archive" / "note.md").read_text(encoding="utf-8")


def test_write_note_force_never_overwrites_an_archived_copy(tmp_path):
    folder = make_project(tmp_path, "P")
    (folder / "archive").mkdir()
    (folder / "archive" / "note.md").write_text("older copy", encoding="utf-8")
    stamp = notes.note_stamp(folder)
    changed_by_someone_else(folder)
    notes.write_note(folder, "---\ntitle: Mine\n---\n", stamp, datetime(2026, 10, 15, 10, 42), force=True)
    assert (folder / "archive" / "note.md").read_text(encoding="utf-8") == "older copy"
    assert "Theirs" in (folder / "archive" / "note (2026-10-15 10-42).md").read_text(encoding="utf-8")


def test_write_note_refuses_text_without_fields_block(tmp_path):
    folder = make_project(tmp_path, "P")
    with pytest.raises(ValueError):
        notes.write_note(folder, "fields block deleted\n", notes.note_stamp(folder), NOW)
    assert (folder / "note.md").read_text(encoding="utf-8") == NOTE
