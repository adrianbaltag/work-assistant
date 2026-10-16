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


# ---------- review fixes ----------

def test_set_fields_updates_every_copy_of_a_duplicated_key():
    text = notes.set_fields("---\nnext: a\nnext: b\n---\n", {"next": "c"})
    assert text == "---\nnext: c\nnext: c\n---\n"


def test_read_history_stops_at_a_top_level_heading():
    text = "## History\n- 2026-10-15 · you · real\n# Notes\n- not history\n"
    assert [h["text"] for h in notes.read_history(text)] == ["real"]


def test_note_stamp_changes_with_size_even_if_time_is_the_same(tmp_path):
    folder = make_project(tmp_path, "P")
    note = folder / "note.md"
    os.utime(note, ns=(5_000_000_000, 5_000_000_000))
    before = notes.note_stamp(folder)
    note.write_text(NOTE + "more\n", encoding="utf-8")
    os.utime(note, ns=(5_000_000_000, 5_000_000_000))   # coarse clock: same time
    assert notes.note_stamp(folder) != before


# ---------- slice 4: sessions\ and raw\ files ----------

def add_file(folder, dir, name, data=b"hello\n"):
    """Create folder/dir/name with these bytes and return its path."""
    path = folder / dir / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return path


def test_list_files_newest_name_first_and_skips_folders_and_hidden(tmp_path):
    folder = make_project(tmp_path, "P")
    add_file(folder, "sessions", "2026-10-14.md")
    add_file(folder, "sessions", "2026-10-15.md", b"abc")
    add_file(folder, "sessions", ".DS_Store")
    (folder / "sessions" / "sub").mkdir()
    files = notes.list_files(folder)
    assert files["sessions"] == [{"name": "2026-10-15.md", "size": 3}, {"name": "2026-10-14.md", "size": 6}]
    assert files["raw"] == []       # missing folder = empty, not an error


def test_file_path_only_plain_names_in_sessions_or_raw(tmp_path):
    folder = make_project(tmp_path, "P")
    assert notes.file_path(folder, "raw", "a.txt") == folder / "raw" / "a.txt"
    assert notes.file_path(folder, "sessions", "a b (1).md") == folder / "sessions" / "a b (1).md"
    for dir, name in [("raw", "../note.md"), ("raw", "x/y.txt"), ("raw", ".hidden"), ("raw", ""),
                      ("raw", ".."), ("archive", "a.txt"), ("..", "a.txt"), ("", "note.md")]:
        assert notes.file_path(folder, dir, name) is None, (dir, name)


def test_read_file_kinds(tmp_path):
    folder = make_project(tmp_path, "P")
    assert notes.read_file(add_file(folder, "raw", "a.txt", "café\n".encode())) == {"kind": "text", "text": "café\n"}
    assert notes.read_file(add_file(folder, "raw", "b.md", b"\xef\xbb\xbfbom\n"))["text"] == "bom\n"
    assert notes.read_file(add_file(folder, "raw", "shot.PNG", b"\x89PNG"))["kind"] == "image"
    assert notes.read_file(add_file(folder, "raw", "c.bin", b"a\x00b"))["kind"] == "other"
    assert notes.read_file(add_file(folder, "raw", "d.xlsx", b"\xff\xfe\xfa"))["kind"] == "other"
    big = add_file(folder, "raw", "huge.log", b"x" * (notes.TEXT_LIMIT + 1))
    assert notes.read_file(big)["kind"] == "other"


def test_write_file_saves_refuses_stale_and_force_archives_theirs(tmp_path):
    folder = make_project(tmp_path, "P")
    path = add_file(folder, "sessions", "s.md", b"old\n")
    stamp = notes.file_stamp(path)
    stamp = notes.write_file(path, folder, "mine 1\n", stamp, NOW)
    assert path.read_text(encoding="utf-8") == "mine 1\n"

    path.write_text("theirs\n", encoding="utf-8")
    os.utime(path, ns=(5_000_000_000, 5_000_000_000))
    with pytest.raises(notes.StaleNote):
        notes.write_file(path, folder, "mine 2\n", stamp, NOW)
    notes.write_file(path, folder, "mine 2\n", stamp, NOW, force=True)
    assert path.read_text(encoding="utf-8") == "mine 2\n"
    assert (folder / "archive" / "sessions" / "s.md").read_text(encoding="utf-8") == "theirs\n"


def test_new_file_creates_folder_and_empty_file_but_never_overwrites(tmp_path):
    folder = make_project(tmp_path, "P")
    path = notes.new_file(folder, "sessions", "2026-10-15.md")
    assert path.read_bytes() == b""
    path.write_text("keep me", encoding="utf-8")
    with pytest.raises(FileExistsError):
        notes.new_file(folder, "sessions", "2026-10-15.md")
    assert path.read_text(encoding="utf-8") == "keep me"


def test_rename_file_refuses_a_taken_name_but_allows_a_case_change(tmp_path):
    folder = make_project(tmp_path, "P")
    a = add_file(folder, "raw", "a.txt", b"A")
    add_file(folder, "raw", "b.txt", b"B")
    with pytest.raises(FileExistsError):
        notes.rename_file(a, "b.txt")
    assert (folder / "raw" / "b.txt").read_bytes() == b"B"
    c = notes.rename_file(a, "c.txt")
    assert c.read_bytes() == b"A" and not a.exists()
    assert notes.rename_file(c, "C.txt").name == "C.txt"
    assert [f["name"] for f in notes.list_files(folder)["raw"]] == ["b.txt", "C.txt"]


def test_archive_file_moves_it_and_never_overwrites(tmp_path):
    folder = make_project(tmp_path, "P")
    notes.archive_file(add_file(folder, "raw", "a.txt", b"first"), folder, NOW)
    notes.archive_file(add_file(folder, "raw", "a.txt", b"second"), folder, datetime(2026, 10, 15, 10, 42))
    assert not (folder / "raw" / "a.txt").exists()
    assert (folder / "archive" / "raw" / "a.txt").read_bytes() == b"first"
    assert (folder / "archive" / "raw" / "a (2026-10-15 10-42).txt").read_bytes() == b"second"


def test_save_upload_goes_to_raw_and_gets_a_suffix_when_taken(tmp_path):
    folder = make_project(tmp_path, "P")
    when = datetime(2026, 10, 15, 14, 30)
    assert notes.save_upload(folder, "shot.png", b"one", when) == "shot.png"
    assert notes.save_upload(folder, "shot.png", b"two", when) == "shot (2026-10-15 14-30).png"
    assert notes.save_upload(folder, "shot.png", b"three", when) == "shot (2026-10-15 14-30 2).png"
    assert (folder / "raw" / "shot.png").read_bytes() == b"one"


# ---------- slice 4 review fixes ----------

def test_archive_file_removes_its_copy_when_the_file_is_locked(tmp_path, monkeypatch):
    """Windows: a file open in Excel can't be deleted. Then nothing changes, and no stray copy is left."""
    folder = make_project(tmp_path, "P")
    path = add_file(folder, "raw", "report.xlsx", b"x")
    def locked(self, *args, **kwargs):
        if self.name == "report.xlsx" and self.parent.name == "raw" and self.parent.parent == folder:
            raise PermissionError("in use")
        return real_unlink(self, *args, **kwargs)
    real_unlink = type(path).unlink
    monkeypatch.setattr(type(path), "unlink", locked)
    with pytest.raises(PermissionError):
        notes.archive_file(path, folder, NOW)
    assert path.exists()
    assert list((folder / "archive" / "raw").iterdir()) == []


# ---------- slice 5: archive projects, list the archive, restore ----------

def test_archive_project_moves_folder_marks_done_and_adds_history(tmp_path):
    folder = make_project(tmp_path, "DEMO-1111")
    target = notes.archive_project(tmp_path, folder, NOW)
    assert target == tmp_path / "_archive" / "DEMO-1111"
    assert not folder.exists()
    text = (target / "note.md").read_text(encoding="utf-8")
    assert notes.parse_note(text)[0]["status"] == "done"
    assert notes.read_history(text)[0]["text"] == "Marked done and archived"
    assert notes.list_projects(tmp_path) == []


def test_archive_project_never_overwrites_an_archived_one(tmp_path):
    (tmp_path / "_archive").mkdir()
    make_project(tmp_path / "_archive", "P", "---\ntitle: old\n---\n")
    target = notes.archive_project(tmp_path, make_project(tmp_path, "P"), datetime(2026, 10, 15, 10, 42))
    assert target.name == "P (2026-10-15 10-42)"
    assert "title: old" in (tmp_path / "_archive" / "P" / "note.md").read_text(encoding="utf-8")


def test_archive_project_folder_name_with_a_dot_gets_suffix_at_the_end(tmp_path):
    (tmp_path / "_archive").mkdir()
    make_project(tmp_path / "_archive", "v1.2 tool")
    target = notes.archive_project(tmp_path, make_project(tmp_path, "v1.2 tool"), datetime(2026, 10, 15, 10, 42))
    assert target.name == "v1.2 tool (2026-10-15 10-42)"


def test_archive_project_locked_folder_changes_nothing(tmp_path, monkeypatch):
    """Windows: a file open in Excel blocks moving the folder. Then the note must stay untouched too."""
    folder = make_project(tmp_path, "P")
    def locked(*args):
        raise PermissionError("in use")
    monkeypatch.setattr(notes.os, "rename", locked)
    with pytest.raises(PermissionError):
        notes.archive_project(tmp_path, folder, NOW)
    assert (folder / "note.md").read_text(encoding="utf-8") == NOTE


def test_list_archive_projects_and_deleted_files(tmp_path):
    notes.archive_project(tmp_path, make_project(tmp_path, "OLD-1"), NOW)
    open_one = make_project(tmp_path, "P")
    notes.archive_file(add_file(open_one, "raw", "a.txt", b"abc"), open_one, NOW)
    notes.archive_file(add_file(open_one, "sessions", "s.md", b"x"), open_one, NOW)
    notes.archive_copy(open_one / "note.md", open_one, NOW)     # a "Save mine anyway" copy
    (open_one / "archive" / "junk").mkdir()                      # unknown sub-folders are not listed

    archive = notes.list_archive(tmp_path)

    [old] = archive["projects"]
    assert (old["id"], old["title"], old["status"], old["files"]) == ("OLD-1", "Fix the RAN alarms", "done", 1)
    assert "body" not in old
    found = {(f["project"], f["dir"], f["name"]) for f in archive["files"]}
    assert found == {("P", "raw", "a.txt"), ("P", "sessions", "s.md"), ("P", "", "note.md")}
    assert next(f for f in archive["files"] if f["name"] == "a.txt")["size"] == 3


def test_list_archive_without_any_archive_is_empty(tmp_path):
    make_project(tmp_path, "P")
    assert notes.list_archive(tmp_path) == {"projects": [], "files": []}


def test_find_archived_only_plain_names_inside_archive(tmp_path):
    notes.archive_project(tmp_path, make_project(tmp_path, "P"), NOW)
    make_project(tmp_path, "OPEN")
    assert notes.find_archived(tmp_path, "P") == tmp_path / "_archive" / "P"
    for bad in ["OPEN", "../OPEN", "", ".hidden", "nope"]:
        assert notes.find_archived(tmp_path, bad) is None


def test_restore_project_sets_active_adds_history_and_never_overwrites(tmp_path):
    notes.archive_project(tmp_path, make_project(tmp_path, "P"), NOW)
    make_project(tmp_path, "P", "---\ntitle: new one\n---\n")    # a new project took the name meanwhile
    when = datetime(2026, 10, 15, 10, 42)

    new_id = notes.restore_project(tmp_path, tmp_path / "_archive" / "P", when)

    assert new_id == "P (2026-10-15 10-42)"
    text = (tmp_path / new_id / "note.md").read_text(encoding="utf-8")
    assert notes.parse_note(text)[0]["status"] == "active"
    assert notes.read_history(text)[0]["text"] == "Restored from archive"
    assert "title: new one" in (tmp_path / "P" / "note.md").read_text(encoding="utf-8")
    assert notes.list_archive(tmp_path)["projects"] == []


def test_restore_file_back_to_its_folder_with_suffix_when_taken(tmp_path):
    folder = make_project(tmp_path, "P")
    notes.archive_file(add_file(folder, "raw", "a.txt", b"old"), folder, NOW)
    add_file(folder, "raw", "a.txt", b"new")
    assert notes.restore_file(folder, "raw", "a.txt", datetime(2026, 10, 15, 10, 42)) == "raw/a (2026-10-15 10-42).txt"
    assert (folder / "raw" / "a.txt").read_bytes() == b"new"
    assert (folder / "raw" / "a (2026-10-15 10-42).txt").read_bytes() == b"old"
    assert notes.list_archive(tmp_path)["files"] == []


def test_restore_note_copy_goes_to_raw_and_never_touches_the_live_note(tmp_path):
    folder = make_project(tmp_path, "P")
    notes.archive_copy(folder / "note.md", folder, NOW)
    (folder / "note.md").write_text("---\ntitle: live\n---\n", encoding="utf-8")
    assert notes.restore_file(folder, "", "note.md", NOW) == "raw/note.md"
    assert (folder / "raw" / "note.md").read_text(encoding="utf-8") == NOTE
    assert "live" in (folder / "note.md").read_text(encoding="utf-8")


def test_archived_file_path_only_plain_names_in_known_places(tmp_path):
    folder = make_project(tmp_path, "P")
    assert notes.archived_file_path(folder, "raw", "a.txt") == folder / "archive" / "raw" / "a.txt"
    assert notes.archived_file_path(folder, "", "note.md") == folder / "archive" / "note.md"
    for dir, name in [("junk", "a.txt"), ("raw", "../a.txt"), ("raw", ".x"), ("raw", ""), ("..", "a.txt")]:
        assert notes.archived_file_path(folder, dir, name) is None


# ---------- + New project ----------

def test_new_project_makes_note_with_all_fields_and_empty_folders(tmp_path):
    folder = notes.new_project(tmp_path, "ABC-123", "Fix alarms", "pending")
    assert folder == tmp_path / "ABC-123"
    assert (folder / "sessions").is_dir() and (folder / "raw").is_dir()
    assert (folder / "note.md").read_text(encoding="utf-8") == (
        "---\ntitle: Fix alarms\nstatus: pending\npriority: normal\nnext:\nblocked_by:\n"
        "jira: ABC-123\nfolder:\ntags:\n---\n\n## Goal\n\n\n## History\n")
    assert notes.read_history((folder / "note.md").read_text(encoding="utf-8")) == []
    assert notes.find_project(tmp_path, "ABC-123") == folder


def test_new_project_defaults_title_to_id_and_no_jira_for_plain_names(tmp_path):
    fields, _ = notes.parse_note((notes.new_project(tmp_path, "my_idea") / "note.md").read_text(encoding="utf-8"))
    assert (fields["title"], fields["status"], fields["jira"]) == ("my_idea", "active", "")


def test_new_project_title_is_kept_on_one_line(tmp_path):
    fields, _ = notes.parse_note((notes.new_project(tmp_path, "P", "  two\nlines ") / "note.md").read_text(encoding="utf-8"))
    assert fields["title"] == "two lines"


@pytest.mark.parametrize("taken", ["open project", "stray folder", "file"])
def test_new_project_never_touches_a_taken_name(tmp_path, taken):
    if taken == "open project":
        make_project(tmp_path, "P")
    elif taken == "stray folder":
        (tmp_path / "P").mkdir()
    else:
        (tmp_path / "P").write_text("x", encoding="utf-8")
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    with pytest.raises(FileExistsError):
        notes.new_project(tmp_path, "P")
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before


def test_new_project_allowed_when_the_id_is_only_in_the_archive(tmp_path):
    notes.archive_project(tmp_path, make_project(tmp_path, "P"), NOW)
    notes.new_project(tmp_path, "P")
    assert notes.find_project(tmp_path, "P") and notes.find_archived(tmp_path, "P")


@pytest.mark.parametrize("bad", ["", "_archive", "../x", ".hidden", "a/b"])
def test_new_project_refuses_unsafe_names(tmp_path, bad):
    with pytest.raises(ValueError):
        notes.new_project(tmp_path, bad)
    assert list(tmp_path.iterdir()) == []


def test_new_project_leaves_nothing_behind_when_writing_fails(tmp_path, monkeypatch):
    """A half-made folder (no note.md) would be invisible in the app and block the name for good."""
    def broken(*args, **kwargs):
        raise PermissionError("disk full")
    monkeypatch.setattr(notes.Path, "write_text", broken)
    with pytest.raises(PermissionError):
        notes.new_project(tmp_path, "P")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("project_id, jira", [("ABC-123", "ABC-123"), ("NET5G-42", "NET5G-42"),
                                              ("phase-2", ""), ("abc-123", ""), ("5G-1", "")])
def test_new_project_fills_jira_only_for_uppercase_ticket_keys(tmp_path, project_id, jira):
    fields, _ = notes.parse_note((notes.new_project(tmp_path, project_id) / "note.md").read_text(encoding="utf-8"))
    assert fields["jira"] == jira
