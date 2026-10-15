"""Slice 1: reading project notes and listing projects (notes.py, no Flask)."""
import os
from datetime import datetime, timedelta

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
