"""S1 safety: a save never empties or half-writes a note, one bad note never blanks the dashboard,
a locked note gives a plain message, and the page only answers to its own address.

All folders are fake (tmp_path) and all text is made up.
"""
from datetime import datetime

import pytest

import notes
import project_note as pn
from app import create_app

NOW = datetime(2026, 10, 23, 9, 30)
NOTE = "---\ntitle: Demo\nstatus: active\n---\nbody text\n\n## History\n- 2026-10-01 · you · first\n"
CP1252_NOTE = "---\ntitle: Café\n---\nbody\n".encode("cp1252")
URL = "/api/projects/DEMO-1"


def make_project(root, folder="DEMO-1", data=NOTE):
    path = root / folder
    path.mkdir(parents=True)
    note = path / "note.md"
    note.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


@pytest.fixture
def client(tmp_path):
    make_project(tmp_path)
    app = create_app(tmp_path)
    app.config.update(TESTING=True)
    return app.test_client()


def locked(*args, **kwargs):
    raise PermissionError(13, "in use")


def temp_files(folder):
    return [p.name for p in folder.iterdir() if p.name.endswith(".tmp")]


# ---------- 1. one safe-save helper ----------

def test_safe_write_writes_utf8_with_lf_line_ends_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "note.md"
    target.write_bytes(b"old")
    notes.safe_write(target, "a\nb é\n")
    assert target.read_bytes() == "a\nb é\n".encode("utf-8")      # LF kept, no CRLF
    assert temp_files(tmp_path) == []


def test_safe_write_of_a_broken_character_changes_nothing(tmp_path):
    target = tmp_path / "note.md"
    target.write_bytes(b"old")
    with pytest.raises(ValueError, match="broken character"):
        notes.safe_write(target, "half an emoji \ud83d")
    assert target.read_bytes() == b"old"
    assert temp_files(tmp_path) == []


def test_safe_write_when_the_file_is_open_elsewhere_says_so_and_cleans_up(tmp_path, monkeypatch):
    target = tmp_path / "note.md"
    target.write_bytes(b"old")
    monkeypatch.setattr(notes.os, "replace", locked)
    with pytest.raises(notes.Locked, match="open in another program"):
        notes.safe_write(target, "new")
    assert target.read_bytes() == b"old"
    assert temp_files(tmp_path) == []


def test_a_lone_surrogate_in_history_gives_400_and_keeps_the_note(tmp_path, client):
    before = (tmp_path / "DEMO-1" / "note.md").read_bytes()
    # The card's Note box (it took the place of "Add a line to the history"): the same promise.
    response = client.post(f"{URL}/message", json={"kind": "note", "text": "\ud83d"})
    assert response.status_code == 400
    assert "broken character" in response.json["error"]
    assert (tmp_path / "DEMO-1" / "note.md").read_bytes() == before


def test_write_file_uses_the_safe_save(tmp_path, monkeypatch):
    folder = make_project(tmp_path)
    monkeypatch.setattr(notes.os, "replace", locked)
    with pytest.raises(PermissionError):
        notes.write_file(folder / "note.md", folder, NOTE + "x", notes.note_stamp(folder), NOW)
    assert (folder / "note.md").read_text(encoding="utf-8") == NOTE


def test_mark_uses_the_safe_save(tmp_path, monkeypatch):
    folder = make_project(tmp_path)
    monkeypatch.setattr(notes.os, "replace", locked)
    with pytest.raises(PermissionError):
        notes.mark(folder, "done", "x", NOW)
    assert (folder / "note.md").read_text(encoding="utf-8") == NOTE


def test_new_project_uses_the_safe_save_and_leaves_no_half_made_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(notes.os, "replace", locked)
    with pytest.raises(PermissionError):
        notes.new_project(tmp_path, "ABC-1", "T")
    assert not (tmp_path / "ABC-1").exists()


def test_new_project_with_a_broken_character_in_the_title_still_works(tmp_path):
    folder = notes.new_project(tmp_path, "ABC-1", "half \ud83d emoji")
    assert notes.read_project(folder)["title"] == "half ? emoji"


def test_project_note_writers_use_the_safe_save(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    card = make_project(projects, "DEMO-42")
    work = tmp_path / "work_jira" / "DEMO-42"
    work.mkdir(parents=True)
    (work / "tracking_log.md").write_text("## Now working on\nM1\n\n## Next up\nM2\n\n## Last update\n", encoding="utf-8")
    monkeypatch.setattr(notes.os, "replace", locked)
    with pytest.raises(PermissionError):
        pn.sync(projects, work, NOW)
    with pytest.raises(PermissionError):
        pn.link_card(card, work)
    assert (card / "note.md").read_text(encoding="utf-8") == NOTE
    with pytest.raises(PermissionError):         # create: a new card gets its Goal written
        pn.create(projects, tmp_path / "work_jira" / "DEMO-43", "T", "a goal", NOW)


def test_fill_jira_uses_the_safe_save(tmp_path, monkeypatch):
    card = make_project(tmp_path, "demo-42")              # a lowercase ticket folder: jira: gets filled
    monkeypatch.setattr(notes.os, "replace", locked)
    with pytest.raises(PermissionError):
        pn.fill_jira(card, "demo-42")
    assert (card / "note.md").read_text(encoding="utf-8") == NOTE


def test_apply_uses_the_safe_save_for_the_session_file_and_the_note(tmp_path, monkeypatch):
    folder = make_project(tmp_path)
    app = create_app(tmp_path)
    app.config.update(TESTING=True)
    proposal = {"fields": [{"field": "next", "value": "x"}], "history_line": "", "session_note": "## Today\nText"}
    stamp = notes.note_stamp(folder)
    monkeypatch.setattr(notes.os, "replace", locked)
    response = app.test_client().post(f"{URL}/apply", json={"proposal": proposal, "stamp": stamp})
    assert response.status_code == 400 and "open in another program" in response.json["error"]
    assert (folder / "note.md").read_text(encoding="utf-8") == NOTE
    assert not (folder / "sessions").exists() or list((folder / "sessions").iterdir()) == []


# ---------- 2. one bad note does not blank the dashboard ----------

def test_dashboard_lists_a_note_saved_as_cp1252_with_a_plain_problem(tmp_path):
    make_project(tmp_path, "BAD-1", CP1252_NOTE)
    make_project(tmp_path, "DEMO-1")
    app = create_app(tmp_path)
    app.config.update(TESTING=True)
    response = app.test_client().get("/api/projects")
    assert response.status_code == 200
    rows = {r["id"]: r for r in response.json["projects"]}
    assert set(rows) == {"BAD-1", "DEMO-1"}
    assert "UTF-8" in rows["BAD-1"]["problem"] and "Notepad" in rows["BAD-1"]["problem"]
    assert rows["BAD-1"]["working_on"] == rows["BAD-1"]["problem"]       # the page already shows working_on
    assert "problem" not in rows["DEMO-1"]


def test_archive_page_lists_a_bad_note_with_a_problem(tmp_path):
    make_project(tmp_path / "_archive", "OLD-1", CP1252_NOTE)
    make_project(tmp_path, "BAD-1", CP1252_NOTE)
    app = create_app(tmp_path)
    app.config.update(TESTING=True)
    response = app.test_client().get("/api/archive")
    assert response.status_code == 200
    assert "UTF-8" in response.json["projects"][0]["problem"]


def test_opening_a_bad_note_gives_a_plain_error_not_a_crash(tmp_path):
    make_project(tmp_path, "BAD-1", CP1252_NOTE)
    app = create_app(tmp_path)
    app.config.update(TESTING=True)
    response = app.test_client().get("/api/projects/BAD-1")
    assert response.status_code == 400
    assert "UTF-8" in response.json["error"]


def test_archive_gone_skips_a_card_whose_note_is_not_utf8(tmp_path):
    projects = tmp_path / "projects"
    make_project(projects, "BAD-1", CP1252_NOTE)
    work = tmp_path / "work_jira"
    (work / "OTHER-1").mkdir(parents=True)
    assert pn.archive_gone(projects, work, NOW) == []


def test_import_missing_skips_a_folder_whose_archived_card_is_not_utf8(tmp_path):
    projects = tmp_path / "projects"
    make_project(projects / "_archive", "BAD-1", CP1252_NOTE)
    work = tmp_path / "work_jira"
    (work / "BAD-1").mkdir(parents=True)
    assert pn.import_missing(projects, work, NOW) == []


# ---------- 3. a locked note, bad bodies, one catch-all ----------

FORM = {"title": "T", "status": "active", "priority": "normal", "working_on": "", "next": "",
        "blocked_by": "", "jira": "", "folder": ""}


def stamp_of(tmp_path):
    return notes.note_stamp(tmp_path / "DEMO-1")


def test_a_locked_note_gives_the_plain_message_on_every_save_route(tmp_path, client, monkeypatch):
    monkeypatch.setattr(notes.os, "replace", locked)
    stamp = stamp_of(tmp_path)
    posts = [("fields", {"fields": FORM, "stamp": stamp}),
             ("note", {"text": NOTE + "more\n", "stamp": stamp}),
             ("message", {"kind": "note", "text": "hello"})]
    for route, body in posts:
        response = client.post(f"{URL}/{route}", json=body)
        assert response.status_code == 400, route
        assert "open in another program" in response.json["error"], route


def test_an_unreadable_note_gives_the_plain_message_on_save(tmp_path, client, monkeypatch):
    def refuse(*args, **kwargs):
        raise PermissionError(13, "in use")
    monkeypatch.setattr(notes.Path, "read_text", refuse)
    response = client.post(f"{URL}/note", json={"text": NOTE, "stamp": "x"})
    assert response.status_code == 400 and "open in another program" in response.json["error"]


def test_a_locked_note_gives_the_plain_message_when_opening_the_card(tmp_path, client, monkeypatch):
    def refuse(*args, **kwargs):
        raise PermissionError(13, "in use")
    monkeypatch.setattr(notes.Path, "read_text", refuse)
    response = client.get(URL)
    assert response.status_code == 400 and "open in another program" in response.json["error"]


def test_a_locked_upload_and_new_file_give_the_plain_message(tmp_path, client, monkeypatch):
    import io
    monkeypatch.setattr(notes.Path, "mkdir", locked)
    monkeypatch.setattr(notes.Path, "touch", locked)
    monkeypatch.setattr(notes.Path, "write_bytes", locked)
    upload = client.post(f"{URL}/upload", data={"files": (io.BytesIO(b"x"), "a.txt")})
    assert upload.status_code == 400 and "open in another program" in upload.json["error"]
    new = client.post(f"{URL}/files/raw", json={"name": "a.txt"})
    assert new.status_code == 400 and "open in another program" in new.json["error"]


def test_saving_a_file_with_a_locked_target_gives_the_plain_message(tmp_path, client, monkeypatch):
    folder = tmp_path / "DEMO-1"
    (folder / "raw").mkdir()
    (folder / "raw" / "a.txt").write_text("hi", encoding="utf-8")
    stamp = notes.file_stamp(folder / "raw" / "a.txt")
    monkeypatch.setattr(notes.os, "replace", locked)
    response = client.post(f"{URL}/files/raw/a.txt", json={"text": "new", "stamp": stamp})
    assert response.status_code == 400 and "open in another program" in response.json["error"]


@pytest.mark.parametrize("path, body", [
    ("fields", {}), ("fields", {"fields": "nope", "stamp": "x"}), ("note", {"stamp": "x"}), ("note", {"text": "x"}),
    ("message", {"kind": "note"}), ("message", {"kind": "note", "text": 5}), ("files/raw", []),
    ("files/raw/a.txt", {"stamp": "x"}), ("files/raw/a.txt/rename", []), ("apply", [1]),
])
def test_a_missing_key_or_wrong_body_gives_a_plain_json_error(tmp_path, client, path, body):
    (tmp_path / "DEMO-1" / "raw").mkdir()
    (tmp_path / "DEMO-1" / "raw" / "a.txt").write_text("hi", encoding="utf-8")
    response = client.post(f"{URL}/{path}", json=body)
    assert response.status_code == 400
    assert response.is_json and response.json["error"]


@pytest.mark.parametrize("path", ["fields", "note", "message", "files/raw", "files/raw/a.txt",
                                  "files/raw/a.txt/rename"])
def test_a_body_that_is_not_json_gives_a_plain_json_error(tmp_path, client, path):
    (tmp_path / "DEMO-1" / "raw").mkdir()
    (tmp_path / "DEMO-1" / "raw" / "a.txt").write_text("hi", encoding="utf-8")
    response = client.post(f"{URL}/{path}", data="not json", content_type="text/plain")
    assert response.status_code == 400
    assert response.is_json and response.json["error"]


def test_restore_file_with_a_non_json_body_gives_a_plain_json_error(client):
    response = client.post("/api/archive/files/restore", data="x", content_type="text/plain")
    assert response.status_code == 400 and response.json["error"]


def test_an_unexpected_crash_answers_json_in_plain_english(tmp_path, client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internals")
    monkeypatch.setattr(notes, "list_projects", boom)
    response = client.get("/api/projects")
    assert response.status_code == 500
    assert response.is_json
    assert "secret internals" not in response.json["error"] and "Reload" in response.json["error"]


def test_http_errors_still_answer_as_before(tmp_path, client):
    assert client.get("/api/projects/nope").status_code == 404
    assert client.get("/no-such-page").status_code == 404
    too_big = create_app(tmp_path)
    too_big.config.update(TESTING=True, MAX_CONTENT_LENGTH=10)
    response = too_big.test_client().post(f"{URL}/upload", data=b"x" * 100, content_type="application/octet-stream")
    assert response.status_code == 413 and "Upload too big" in response.json["error"]


# ---------- 4. only the page's own address ----------

def test_a_foreign_host_header_is_refused(client):
    assert client.get("/api/projects", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/projects", headers={"Host": "evil.example:5050"}).status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:5050", "localhost", "localhost:5050"])
def test_the_pages_own_addresses_work(client, host):
    assert client.get("/api/projects", headers={"Host": host}).status_code == 200


# ---------- 5. archive / restore that fails half-way ----------

def test_archive_that_fails_while_marking_puts_the_folder_back(tmp_path):
    folder = make_project(tmp_path, "DEMO-1", CP1252_NOTE)       # mark can't read this note
    with pytest.raises(ValueError):
        notes.archive_project(tmp_path, folder, NOW)
    assert (folder / "note.md").read_bytes() == CP1252_NOTE
    assert list((tmp_path / "_archive").iterdir()) == []


def test_restore_that_fails_while_marking_puts_the_folder_back(tmp_path):
    archived = make_project(tmp_path / "_archive", "DEMO-1", CP1252_NOTE)
    with pytest.raises(ValueError):
        notes.restore_project(tmp_path, archived, NOW)
    assert (archived / "note.md").read_bytes() == CP1252_NOTE
    assert not (tmp_path / "DEMO-1").exists()


def test_archive_with_a_locked_note_answers_plain_and_keeps_the_project_open(tmp_path, client, monkeypatch):
    monkeypatch.setattr(notes.os, "replace", locked)
    response = client.post(f"{URL}/archive")
    assert response.status_code == 400 and "open in another program" in response.json["error"]
    assert (tmp_path / "DEMO-1" / "note.md").is_file()


# ---------- 6. a field value stays on one line ----------

@pytest.mark.parametrize("breaker", [" ", "\x0b", "\x0c", "\x1c", "\x85", "\r", "\n", " "])
def test_set_fields_cannot_split_a_value_over_lines(breaker):
    text = notes.set_fields("---\ntitle: T\n---\nbody\n", {"next": f"a{breaker}b: c", "title": f"x{breaker}y"})
    fields, body = notes.parse_note(text)
    assert fields == {"title": "x y", "next": "a b: c"}
    assert body == "body\n"


# ---------- 7. small ones ----------

def test_add_history_on_a_note_without_a_final_newline_keeps_the_heading_on_its_own_line():
    text = notes.add_history("---\ntitle: T\n---\n\n## History", "hello", "2026-10-23")
    assert text.endswith("## History\n- 2026-10-23 · you · hello\n")
    assert [h["text"] for h in notes.read_history(text)] == ["hello"]


def test_restore_gives_the_card_its_plain_id_back_not_the_time_suffix(tmp_path, client):
    make_project(tmp_path / "_archive", "DEMO-9 (2026-10-24 10-00)")
    response = client.post("/api/archive/projects/DEMO-9 (2026-10-24 10-00)/restore")
    assert response.json == {"id": "DEMO-9"}
    assert (tmp_path / "DEMO-9" / "note.md").is_file()


def test_restore_keeps_a_suffix_only_when_the_plain_id_is_taken(tmp_path, client):
    make_project(tmp_path, "DEMO-9")
    make_project(tmp_path / "_archive", "DEMO-9 (2026-10-24 10-00)")
    new_id = client.post("/api/archive/projects/DEMO-9 (2026-10-24 10-00)/restore").json["id"]
    assert new_id.startswith("DEMO-9 (")
    assert (tmp_path / "DEMO-9" / "note.md").is_file() and (tmp_path / new_id / "note.md").is_file()
