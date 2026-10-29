"""Slice 2: the Flask app serves the dashboard page and the projects as JSON."""
import os
import time
from datetime import datetime

import pytest

import app as app_module
import slack_inbox
from app import create_app, load_settings


def make_project(root, folder, fields, days_ago=0):
    """Create root/folder/note.md with these fields, last changed `days_ago` days ago."""
    path = root / folder
    path.mkdir()
    lines = "".join(f"{k}: {v}\n" for k, v in fields.items())
    note = path / "note.md"
    note.write_text(f"---\n{lines}---\nbody text\n", encoding="utf-8")
    stamp = time.time() - days_ago * 86400
    os.utime(note, (stamp, stamp))


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    app.config.update(TESTING=True)
    return app.test_client()


# ---------- pages ----------

def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Your projects" in response.text


# ---------- /api/projects ----------

def test_api_projects_empty_folder_gives_empty_list(client):
    assert client.get("/api/projects").json["projects"] == []


def test_api_projects_returns_dashboard_rows(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Old one"}, days_ago=10)
    make_project(tmp_path, "DEMO-2222", {"title": "Hot one", "priority": "critical"})

    rows = client.get("/api/projects").json["projects"]

    assert [r["id"] for r in rows] == ["DEMO-2222", "DEMO-1111"]   # critical first
    assert rows[1]["quiet"] is True
    assert rows[1]["days_ago"] == 10
    assert "body" not in rows[0]        # the list doesn't need the note text


def test_api_projects_sends_today_for_the_page_header(client):
    assert client.get("/api/projects").json["today"] == time.strftime("%Y-%m-%d")


# ---------- settings.ini ----------

def test_load_settings_reads_windows_path_without_section_header(tmp_path):
    ini = tmp_path / "settings.ini"
    ini.write_text("projects_folder=C:\\Users\\me\\Desktop\\projects\n"
                   "jira_url=https://jira.example.com\n", encoding="utf-8")
    settings = load_settings(ini)
    assert settings["projects_folder"] == "C:\\Users\\me\\Desktop\\projects"
    assert settings["jira_url"] == "https://jira.example.com"


def test_load_settings_missing_file_explains_what_to_do(tmp_path):
    with pytest.raises(SystemExit, match="settings.ini.example"):
        load_settings(tmp_path / "settings.ini")


# ---------- slice 3: one project card ----------

def open_card(client, project_id="DEMO-1111"):
    return client.get(f"/api/projects/{project_id}").json


FORM = {"title": "Fix alarms", "status": "pending", "priority": "high", "working_on": "M2 — parse", "next": "call vendor",
        "blocked_by": "IT", "jira": "DEMO-1111", "folder": ""}


def test_api_project_returns_fields_text_stamp_and_history(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Fix alarms", "status": "pending"}, days_ago=2)
    card = open_card(client)
    assert card["project"]["title"] == "Fix alarms"
    assert card["project"]["days_ago"] == 2
    assert card["text"].startswith("---\ntitle: Fix alarms\n")
    assert card["stamp"]
    assert card["history"] == []


def test_api_project_unknown_or_unsafe_id_is_404(tmp_path, client):
    (tmp_path / "_archive").mkdir()
    for bad in ["missing", "_archive", "..", ".hidden"]:
        assert client.get(f"/api/projects/{bad}").status_code == 404, bad


def test_save_fields_writes_note_and_dashboard_sees_it(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Old"})
    stamp = open_card(client)["stamp"]
    response = client.post("/api/projects/DEMO-1111/fields", json={"fields": FORM, "stamp": stamp})
    assert response.status_code == 200
    assert response.json["stamp"] != stamp
    row = client.get("/api/projects").json["projects"][0]
    assert (row["title"], row["working_on"], row["next"], row["blocked_by"]) == (
        "Fix alarms", "M2 — parse", "call vendor", "IT")


def test_save_fields_needs_a_title_and_known_choices(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Old"})
    stamp = open_card(client)["stamp"]
    for bad in [{"title": "  "}, {"status": "done"}, {"priority": "urgent"}]:
        response = client.post("/api/projects/DEMO-1111/fields",
                               json={"fields": {**FORM, **bad}, "stamp": stamp})
        assert response.status_code == 400, bad
        assert response.json["error"]


def test_save_fields_conflict_then_save_mine_anyway(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Old"})
    stamp = open_card(client)["stamp"]
    note = tmp_path / "DEMO-1111" / "note.md"
    note.write_text("---\ntitle: Claude's\n---\n", encoding="utf-8")
    os.utime(note, ns=(5_000_000_000, 5_000_000_000))

    first = client.post("/api/projects/DEMO-1111/fields", json={"fields": FORM, "stamp": stamp})
    assert first.status_code == 409
    assert "Claude's" in note.read_text(encoding="utf-8")       # nothing written yet

    forced = client.post("/api/projects/DEMO-1111/fields",
                         json={"fields": FORM, "stamp": stamp, "force": True})
    assert forced.status_code == 200
    assert "title: Fix alarms" in note.read_text(encoding="utf-8")
    assert (tmp_path / "DEMO-1111" / "archive" / "note.md").is_file()


def test_save_raw_note(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Old"})
    stamp = open_card(client)["stamp"]
    response = client.post("/api/projects/DEMO-1111/note",
                           json={"text": "---\ntitle: Raw edit\n---\nnew body\n", "stamp": stamp})
    assert response.status_code == 200
    assert open_card(client)["project"]["title"] == "Raw edit"


def test_save_raw_note_without_fields_block_is_refused(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Old"})
    stamp = open_card(client)["stamp"]
    response = client.post("/api/projects/DEMO-1111/note", json={"text": "oops\n", "stamp": stamp})
    assert response.status_code == 400
    assert open_card(client)["project"]["title"] == "Old"


def test_add_history_line(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Old"})
    stamp = open_card(client)["stamp"]
    response = client.post("/api/projects/DEMO-1111/history",
                           json={"text": "Senior said: Northeast only", "stamp": stamp})
    assert response.status_code == 200
    first = open_card(client)["history"][0]
    assert (first["who"], first["text"]) == ("you", "Senior said: Northeast only")
    assert first["date"] == time.strftime("%Y-%m-%d")


def test_add_history_line_to_note_without_fields_block(tmp_path, client):
    (tmp_path / "loose").mkdir()
    (tmp_path / "loose" / "note.md").write_text("just text\n", encoding="utf-8")
    stamp = open_card(client, "loose")["stamp"]
    response = client.post("/api/projects/loose/history", json={"text": "first", "stamp": stamp})
    assert response.status_code == 200
    assert open_card(client, "loose")["history"][0]["text"] == "first"


# ---------- slice 4: sessions\ and raw\ files ----------

def make_file(root, dir, name, data=b"hello\n"):
    path = root / "DEMO-1111" / dir / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return path


URL = "/api/projects/DEMO-1111/files"


def test_card_lists_session_and_raw_files(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    make_file(tmp_path, "sessions", "2026-10-15.md")
    assert open_card(client)["files"] == {"sessions": [{"name": "2026-10-15.md", "size": 6}], "raw": []}


def test_open_text_file_image_bytes_and_bad_paths(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    make_file(tmp_path, "raw", "a b.txt", b"text\n")
    make_file(tmp_path, "raw", "shot.png", b"\x89PNG")
    opened = client.get(f"{URL}/raw/a%20b.txt").json
    assert (opened["kind"], opened["text"]) == ("text", "text\n") and opened["stamp"]
    assert client.get(f"{URL}/raw/shot.png").json["kind"] == "image"
    assert client.get(f"{URL}/raw/shot.png/bytes").data == b"\x89PNG"
    for bad in ["raw/missing.txt", "archive/a%20b.txt", "raw/..%2Fnote.md", "raw/.hidden"]:
        assert client.get(f"{URL}/{bad}").status_code == 404, bad


def test_new_file_cleans_the_name_and_refuses_a_taken_one(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    response = client.post(f"{URL}/sessions", json={"name": "my notes?.md"})
    assert response.json["name"] == "my_notes.md"
    assert (tmp_path / "DEMO-1111" / "sessions" / "my_notes.md").is_file()
    assert client.post(f"{URL}/sessions", json={"name": "my notes?.md"}).status_code == 400
    assert client.post(f"{URL}/sessions", json={"name": ".."}).status_code == 400
    assert client.post(f"{URL}/archive", json={"name": "x.md"}).status_code == 404


def test_save_file_conflict_then_save_mine_anyway(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    path = make_file(tmp_path, "sessions", "s.md", b"old\n")
    stamp = client.get(f"{URL}/sessions/s.md").json["stamp"]
    path.write_text("theirs\n", encoding="utf-8")
    os.utime(path, ns=(5_000_000_000, 5_000_000_000))
    assert client.post(f"{URL}/sessions/s.md", json={"text": "mine\n", "stamp": stamp}).status_code == 409
    forced = client.post(f"{URL}/sessions/s.md", json={"text": "mine\n", "stamp": stamp, "force": True})
    assert forced.status_code == 200 and forced.json["stamp"]
    assert path.read_text(encoding="utf-8") == "mine\n"


def test_save_refuses_a_file_that_is_not_text(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    path = make_file(tmp_path, "raw", "shot.png", b"\x89PNG")
    stamp = client.get(f"{URL}/raw/shot.png").json["stamp"]
    assert client.post(f"{URL}/raw/shot.png", json={"text": "oops", "stamp": stamp}).status_code == 400
    assert path.read_bytes() == b"\x89PNG"


def test_rename_and_delete_file(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    make_file(tmp_path, "raw", "a.txt")
    make_file(tmp_path, "raw", "b.txt")
    assert client.post(f"{URL}/raw/a.txt/rename", json={"name": "b.txt"}).status_code == 400
    assert client.post(f"{URL}/raw/a.txt/rename", json={"name": "c d.txt"}).json["name"] == "c_d.txt"
    assert client.post(f"{URL}/raw/c_d.txt/delete").status_code == 200
    project = tmp_path / "DEMO-1111"
    assert (project / "archive" / "raw" / "c_d.txt").is_file()
    assert [f["name"] for f in open_card(client)["files"]["raw"]] == ["b.txt"]


def test_upload_goes_to_raw_and_never_overwrites(tmp_path, client):
    import io
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    make_file(tmp_path, "raw", "shot.png", b"old")
    response = client.post("/api/projects/DEMO-1111/upload", content_type="multipart/form-data",
                           data={"files": [(io.BytesIO(b"new"), "shot.png"), (io.BytesIO(b"t"), "my log.txt")]})
    names = response.json["names"]
    assert names[0].startswith("shot (") and names[1] == "my_log.txt"
    assert (tmp_path / "DEMO-1111" / "raw" / "shot.png").read_bytes() == b"old"


def test_upload_too_big_gives_a_clear_error(tmp_path):
    import io
    app = create_app(tmp_path)
    app.config.update(TESTING=True, MAX_CONTENT_LENGTH=10)
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    response = app.test_client().post("/api/projects/DEMO-1111/upload", content_type="multipart/form-data",
                                      data={"files": [(io.BytesIO(b"x" * 100), "big.bin")]})
    assert response.status_code == 413 and "too big" in response.json["error"]


# ---------- slice 4 review fixes ----------

def test_requests_from_other_websites_are_refused(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    make_file(tmp_path, "raw", "a.txt")
    evil = client.post(f"{URL}/raw/a.txt/delete", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert (tmp_path / "DEMO-1111" / "raw" / "a.txt").is_file()
    ours = client.post(f"{URL}/raw/a.txt/delete", headers={"Origin": "http://localhost"})
    assert ours.status_code == 200


def test_bytes_only_serves_images(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    make_file(tmp_path, "raw", "page.html", b"<script>alert(1)</script>")
    assert client.get(f"{URL}/raw/page.html/bytes").status_code == 404


def test_locked_file_gives_a_clear_error(tmp_path, client, monkeypatch):
    import notes
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    make_file(tmp_path, "raw", "a.txt")
    def locked(*args, **kwargs):
        raise PermissionError("in use")
    monkeypatch.setattr(notes, "archive_file", locked)
    monkeypatch.setattr(notes, "rename_file", locked)
    for path, body in [("delete", None), ("rename", {"name": "b.txt"})]:
        response = client.post(f"{URL}/raw/a.txt/{path}", json=body)
        assert response.status_code == 400 and "open in another program" in response.json["error"], path


# ---------- slice 5: Archive page, Mark done & archive, Restore ----------

def test_archive_project_then_archive_page_then_restore(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "Old work", "status": "pending"})

    assert client.post("/api/projects/DEMO-1111/archive").status_code == 200
    assert client.get("/api/projects").json["projects"] == []
    assert client.get("/api/projects/DEMO-1111").status_code == 404
    [row] = client.get("/api/archive").json["projects"]
    assert (row["id"], row["title"], row["status"]) == ("DEMO-1111", "Old work", "done")

    restored = client.post("/api/archive/projects/DEMO-1111/restore")
    assert restored.json == {"id": "DEMO-1111"}
    card = open_card(client)
    assert card["project"]["status"] == "active"
    assert [h["text"] for h in card["history"]] == ["Restored from archive", "Marked done and archived"]
    assert client.get("/api/archive").json["projects"] == []


def test_archive_page_lists_and_restores_deleted_files(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    make_file(tmp_path, "raw", "a.txt")
    client.post(f"{URL}/raw/a.txt/delete")
    [row] = client.get("/api/archive").json["files"]
    assert (row["project"], row["title"], row["dir"], row["name"]) == ("DEMO-1111", "P", "raw", "a.txt")

    restored = client.post("/api/archive/files/restore", json={"project": "DEMO-1111", "dir": "raw", "name": "a.txt"})
    assert restored.json == {"where": "raw/a.txt"}
    assert (tmp_path / "DEMO-1111" / "raw" / "a.txt").is_file()
    assert client.get("/api/archive").json["files"] == []


def test_restore_unknown_or_unsafe_targets_is_404(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    assert client.post("/api/archive/projects/DEMO-1111/restore").status_code == 404   # open, not archived
    assert client.post("/api/archive/projects/nope/restore").status_code == 404
    assert client.post("/api/projects/nope/archive").status_code == 404
    for body in [{"project": "DEMO-1111", "dir": "raw", "name": "missing.txt"},
                 {"project": "DEMO-1111", "dir": "raw", "name": "../note.md"},
                 {"project": "../x", "dir": "raw", "name": "a.txt"},
                 {"project": "DEMO-1111", "dir": "junk", "name": "a.txt"}]:
        assert client.post("/api/archive/files/restore", json=body).status_code == 404, body


def test_archive_and_restore_locked_give_a_clear_error(tmp_path, client, monkeypatch):
    import notes
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    def locked(*args, **kwargs):
        raise PermissionError("in use")
    monkeypatch.setattr(notes.os, "rename", locked)
    response = client.post("/api/projects/DEMO-1111/archive")
    assert response.status_code == 400 and "open in another program" in response.json["error"]
    assert client.get("/api/projects").json["projects"][0]["status"] == "active"


def test_archive_requests_from_other_websites_are_refused(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    evil = client.post("/api/projects/DEMO-1111/archive", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert (tmp_path / "DEMO-1111" / "note.md").is_file()


# ---------- slice 6: Open notes folder, Open in Jira ----------

def test_open_folder_asks_the_computer_to_open_the_project_folder(tmp_path, client, monkeypatch):
    import app as app_module
    opened = []
    monkeypatch.setattr(app_module, "open_in_file_manager", opened.append)   # fake: no real window in tests
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    assert client.post("/api/projects/DEMO-1111/open-folder").json == {"ok": True}
    assert opened == [tmp_path / "DEMO-1111"]


def test_open_folder_unknown_project_or_other_website_does_nothing(tmp_path, client, monkeypatch):
    import app as app_module
    opened = []
    monkeypatch.setattr(app_module, "open_in_file_manager", opened.append)
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    assert client.post("/api/projects/nope/open-folder").status_code == 404
    evil = client.post("/api/projects/DEMO-1111/open-folder", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert opened == []


def test_open_folder_failure_gives_a_clear_error(tmp_path, client, monkeypatch):
    import app as app_module
    def broken(path):
        raise OSError("no file manager")
    monkeypatch.setattr(app_module, "open_in_file_manager", broken)
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    response = client.post("/api/projects/DEMO-1111/open-folder")
    assert response.status_code == 400 and "Could not open" in response.json["error"]


def test_card_sends_jira_url_without_trailing_slash(tmp_path):
    app = create_app(tmp_path, jira_url="https://jira.example.com/")
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    assert app.test_client().get("/api/projects/DEMO-1111").json["jira_url"] == "https://jira.example.com"


def test_card_jira_url_is_empty_when_not_set(tmp_path, client):
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    assert client.get("/api/projects/DEMO-1111").json["jira_url"] == ""


def test_jira_url_without_https_counts_as_not_set(tmp_path):
    """'jira.example.com' alone would open as a page of this app, not Jira."""
    app = create_app(tmp_path, jira_url="jira.example.com")
    make_project(tmp_path, "DEMO-1111", {"title": "P"})
    assert app.test_client().get("/api/projects/DEMO-1111").json["jira_url"] == ""


def test_open_in_file_manager_uses_explorer_on_windows_and_open_on_mac(tmp_path, monkeypatch):
    import app as app_module
    calls = []
    monkeypatch.setattr(app_module.os, "startfile", calls.append, raising=False)   # only exists on Windows
    monkeypatch.setattr(app_module.subprocess, "run", lambda args, check: calls.append(args))
    monkeypatch.setattr(app_module.sys, "platform", "win32")
    app_module.open_in_file_manager(tmp_path)
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    app_module.open_in_file_manager(tmp_path)
    assert calls == [tmp_path, ["open", str(tmp_path)]]


# ---------- + New project ----------

def test_new_project_creates_it_and_cleans_the_name(tmp_path, client):
    response = client.post("/api/projects", json={"id": "my idea", "title": "", "status": "idea"})
    assert response.json == {"id": "my_idea"}
    card = client.get("/api/projects/my_idea").json["project"]
    assert (card["title"], card["status"], card["priority"], card["jira"]) == ("my_idea", "idea", "normal", "")


def test_new_project_fills_jira_for_ticket_ids(client):
    client.post("/api/projects", json={"id": "ABC-123", "title": "Fix alarms", "status": "active"})
    assert client.get("/api/projects/ABC-123").json["project"]["jira"] == "ABC-123"


def test_new_project_name_taken_is_a_clear_error_and_changes_nothing(tmp_path, client):
    make_project(tmp_path, "P", {"title": "old"})
    response = client.post("/api/projects", json={"id": "P", "title": "new", "status": "active"})
    assert response.status_code == 400
    assert "already exists" in response.json["error"]
    assert "title: old" in (tmp_path / "P" / "note.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("body", [{"id": "???", "status": "active"}, {"id": "P", "status": "done"}, {}])
def test_new_project_bad_input_is_refused(tmp_path, client, body):
    response = client.post("/api/projects", json=body)
    assert response.status_code == 400 and response.json["error"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("body", [{"id": None, "status": "active"}, ["ABC-123"], "ABC-123"])
def test_new_project_null_id_or_non_object_body_is_a_400(tmp_path, client, body):
    response = client.post("/api/projects", json=body)
    assert response.status_code == 400 and response.json["error"]
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def work_client(tmp_path):
    (tmp_path / "projects").mkdir()
    (tmp_path / "work_jira").mkdir()
    app = create_app(tmp_path / "projects", work_jira_folder=str(tmp_path / "work_jira"))
    app.config.update(TESTING=True)
    return app.test_client()


def test_new_work_project_also_makes_the_work_jira_folder(tmp_path, work_client):
    response = work_client.post("/api/projects", json={"id": "ABC-123", "title": "Alarms", "status": "active",
                                                       "work": True, "description": "Fix it.", "created_by": "Mike"})
    assert response.json == {"id": "ABC-123"}
    ticket = (tmp_path / "work_jira" / "ABC-123" / "ticket.md").read_text(encoding="utf-8")
    assert "Created by: Mike" in ticket and "Fix it." in ticket
    card = work_client.get("/api/projects/ABC-123").json["project"]
    assert (card["source"], card["folder"]) == ("work_jira", str(tmp_path / "work_jira" / "ABC-123"))


def test_new_work_project_with_a_lowercase_ticket_id_uses_capitals_everywhere(tmp_path, work_client):
    response = work_client.post("/api/projects", json={"id": "abc-123", "title": "Alarms", "status": "active",
                                                       "work": True})
    assert response.json == {"id": "ABC-123"}
    assert [f.name for f in (tmp_path / "work_jira").iterdir()] == ["ABC-123"]
    assert work_client.get("/api/projects/ABC-123").json["project"]["jira"] == "ABC-123"


def test_new_personal_project_name_is_never_capitalised(work_client):
    assert work_client.post("/api/projects", json={"id": "phase-2", "status": "idea"}).json == {"id": "phase-2"}


def test_new_personal_project_stays_out_of_work_jira(tmp_path, work_client):
    work_client.post("/api/projects", json={"id": "my idea", "status": "idea", "work": False})
    assert list((tmp_path / "work_jira").iterdir()) == []
    assert "source" not in work_client.get("/api/projects/my_idea").json["project"]


def test_new_work_project_keeps_an_existing_work_jira_folder(tmp_path, work_client):
    (tmp_path / "work_jira" / "ABC-1").mkdir()
    (tmp_path / "work_jira" / "ABC-1" / "notes.md").write_text("mine", encoding="utf-8")
    response = work_client.post("/api/projects", json={"id": "ABC-1", "status": "active", "work": True, "description": "x"})
    assert [p.name for p in (tmp_path / "work_jira" / "ABC-1").iterdir()] == ["notes.md"]
    assert work_client.get("/api/projects/ABC-1").json["project"]["source"] == "work_jira"
    assert "already existed" in response.json["note"]      # the page tells the person the description was not used


def test_new_work_project_in_a_new_folder_has_no_note(work_client):
    response = work_client.post("/api/projects", json={"id": "ABC-2", "status": "active", "work": True})
    assert "note" not in response.json


def test_new_work_project_without_the_setting_is_refused_and_changes_nothing(tmp_path, client):
    response = client.post("/api/projects", json={"id": "ABC-1", "status": "active", "work": True})
    assert response.status_code == 400 and "work_jira_folder=" in response.json["error"]
    assert list(tmp_path.iterdir()) == []


def test_new_work_project_name_taken_leaves_work_jira_alone(tmp_path, work_client):
    make_project(tmp_path / "projects", "P", {"title": "old"})
    response = work_client.post("/api/projects", json={"id": "P", "status": "active", "work": True})
    assert response.status_code == 400 and list((tmp_path / "work_jira").iterdir()) == []


def test_home_page_greys_the_work_box_without_the_setting(client, work_client):
    assert b'id="np-work" disabled' in client.get("/").data
    assert b'id="np-work" checked' in work_client.get("/").data


def test_new_project_null_title_means_no_title(client):
    client.post("/api/projects", json={"id": "P", "title": None, "status": "active"})
    assert client.get("/api/projects/P").json["project"]["title"] == "P"


@pytest.mark.parametrize("error, says", [(PermissionError("no"), "Could not create"), (ValueError("x"), "can't be used")])
def test_new_project_other_failures_give_a_readable_json_error(client, monkeypatch, error, says):
    import notes
    def broken(*args):
        raise error
    monkeypatch.setattr(notes, "new_project", broken)
    response = client.post("/api/projects", json={"id": "P", "status": "active"})
    assert response.status_code == 400 and says in response.json["error"]


# ---------- Ask Claude (project panel) ----------

from tests.test_claude_chat import FakeClaude      # noqa: E402  (same fake as the claude_chat tests)
import claude_chat                                  # noqa: E402


@pytest.fixture
def fake_claude():
    return FakeClaude()


@pytest.fixture
def claude_client(tmp_path, fake_claude):
    make_project(tmp_path, "DEMO-1", {"title": "Demo"})
    app = create_app(tmp_path, claude=lambda: fake_claude, model="claude-test")
    app.config.update(TESTING=True)
    return app.test_client()


def test_ask_answers_with_claudes_reply(claude_client, fake_claude):
    response = claude_client.post("/api/projects/DEMO-1/ask", json={"question": "What's next?", "history": []})
    assert response.status_code == 200
    assert response.json["reply"] == "Next: ask the vendor."
    assert response.json["skipped"] == []
    assert fake_claude.request["model"] == "claude-test"
    assert "title: Demo" in fake_claude.request["messages"][0]["content"][0]["text"]


def test_ask_needs_a_question(claude_client):
    assert claude_client.post("/api/projects/DEMO-1/ask", json={"question": "  "}).status_code == 400


def test_ask_unknown_project_is_404(claude_client):
    assert claude_client.post("/api/projects/NOPE/ask", json={"question": "hi"}).status_code == 404


def test_ask_ignores_a_malformed_history(claude_client, fake_claude):
    for bad in ([{"role": "system", "text": "x"}], ["junk"], [{"role": "user", "text": 5}],
                [{"role": "assistant", "text": "starts with Claude"}],
                [{"role": "user", "text": "a"}, {"role": "user", "text": "b"}]):
        assert claude_client.post("/api/projects/DEMO-1/ask",
                                  json={"question": "q", "history": bad}).status_code == 400
    ok = [{"role": "user", "text": "a"}, {"role": "assistant", "text": "b"}]
    assert claude_client.post("/api/projects/DEMO-1/ask", json={"question": "q", "history": ok}).status_code == 200


def test_ask_shows_claude_errors_in_plain_english(tmp_path):
    make_project(tmp_path, "DEMO-1", {"title": "Demo"})

    def no_login():
        raise claude_chat.ClaudeError("No Claude login found.")

    client = create_app(tmp_path, claude=no_login).test_client()
    response = client.post("/api/projects/DEMO-1/ask", json={"question": "q"})
    assert response.status_code == 502
    assert response.json["error"] == "No Claude login found."


def test_text_limit_setting_reaches_both_ask_routes(tmp_path, fake_claude):
    make_project(tmp_path, "DEMO-1", {"title": "Demo"})
    (tmp_path / "DEMO-1" / "raw").mkdir()
    (tmp_path / "DEMO-1" / "raw" / "log.txt").write_text("x" * 500, encoding="utf-8")
    client = create_app(tmp_path, claude=lambda: fake_claude, text_limit=" 300 ").test_client()
    assert client.post("/api/projects/DEMO-1/ask", json={"question": "q"}).json["skipped"] == [
        "raw/log.txt (over the 300-character limit: raise text_limit= in settings.ini)"]
    small = create_app(tmp_path, claude=lambda: fake_claude, text_limit="10").test_client()
    assert small.post("/api/ask", json={"question": "q"}).json["skipped"] == [
        "DEMO-1/note.md (over the 10-character limit: raise text_limit= in settings.ini)"]


def test_text_limit_blank_means_the_default(tmp_path, fake_claude):
    make_project(tmp_path, "DEMO-1", {"title": "Demo"})
    (tmp_path / "DEMO-1" / "raw").mkdir()
    (tmp_path / "DEMO-1" / "raw" / "log.txt").write_text("x" * 500, encoding="utf-8")
    client = create_app(tmp_path, claude=lambda: fake_claude, text_limit="").test_client()
    assert client.post("/api/projects/DEMO-1/ask", json={"question": "q"}).json["skipped"] == []


@pytest.mark.parametrize("bad", ["abc", "200,000", "0", "-5", "1.5"])
def test_text_limit_that_is_not_a_whole_number_stops_the_app_with_a_clear_message(tmp_path, bad):
    with pytest.raises(SystemExit, match="text_limit="):
        create_app(tmp_path, text_limit=bad)


def test_model_defaults_to_sonnet(tmp_path, fake_claude):
    make_project(tmp_path, "DEMO-1", {"title": "Demo"})
    client = create_app(tmp_path, claude=lambda: fake_claude).test_client()
    client.post("/api/projects/DEMO-1/ask", json={"question": "q"})
    assert fake_claude.request["model"] == "claude-sonnet-5-5"


# ---------- Ask Claude: the global page asks about every open project ----------

def test_global_ask_reads_every_open_note_and_answers(tmp_path, fake_claude):
    make_project(tmp_path, "DEMO-1", {"title": "Report"})
    make_project(tmp_path, "DEMO-2", {"title": "Parser"})
    client = create_app(tmp_path, claude=lambda: fake_claude, model="claude-test").test_client()
    response = client.post("/api/ask", json={"question": "Which projects are blocked?", "history": []})
    assert response.status_code == 200
    assert response.json["reply"] == "Next: ask the vendor."
    assert response.json["skipped"] == []
    sent = "\n".join(b["text"] for b in fake_claude.request["messages"][0]["content"] if b["type"] == "text")
    assert "title: Report" in sent and "title: Parser" in sent
    assert fake_claude.request["system"] == claude_chat.ALL_SYSTEM
    assert "tools" not in fake_claude.request          # answers only: no proposals here


def test_global_ask_never_returns_a_proposal(tmp_path):
    make_project(tmp_path, "DEMO-1", {"title": "Report"})
    fake = FakeClaude(text="Done.", proposal=PROPOSAL)
    response = create_app(tmp_path, claude=lambda: fake).test_client().post("/api/ask", json={"question": "q"})
    assert "proposal" not in response.json


def test_global_ask_checks_question_and_history(claude_client):
    assert claude_client.post("/api/ask", json={"question": " "}).status_code == 400
    bad = [{"role": "assistant", "text": "starts with Claude"}]
    assert claude_client.post("/api/ask", json={"question": "q", "history": bad}).status_code == 400


def test_global_ask_shows_claude_errors_in_plain_english(tmp_path):
    def no_login():
        raise claude_chat.ClaudeError("No Claude login found.")

    response = create_app(tmp_path, claude=no_login).test_client().post("/api/ask", json={"question": "q"})
    assert response.status_code == 502 and response.json["error"] == "No Claude login found."


# ---------- Ask Claude: Approve applies a proposal ----------

PROPOSAL = {"fields": [{"field": "next", "value": "send the report"}, {"field": "status", "value": "pending"}],
            "history_line": "Vendor replied", "session_note": "## Today\nRead the vendor reply."}


def test_ask_lets_the_project_panel_propose_and_returns_the_proposal(tmp_path):
    make_project(tmp_path, "DEMO-1", {"title": "Demo"})
    fake = FakeClaude(text="My update:", proposal=PROPOSAL)
    client = create_app(tmp_path, claude=lambda: fake).test_client()
    response = client.post("/api/projects/DEMO-1/ask", json={"question": "Update it"})
    assert fake.request["tools"][0]["name"] == "propose_changes"
    assert response.json["proposal"] == PROPOSAL
    assert response.json["stamp"]


def apply(client, tmp_path, proposal=PROPOSAL, stamp=None):
    import notes
    stamp = stamp or notes.note_stamp(tmp_path / "DEMO-1")
    return client.post("/api/projects/DEMO-1/apply", json={"proposal": proposal, "stamp": stamp})


def test_apply_saves_fields_history_line_and_session_note(tmp_path, claude_client):
    response = apply(claude_client, tmp_path)
    assert response.status_code == 200
    note = (tmp_path / "DEMO-1" / "note.md").read_text()
    assert "next: send the report\n" in note and "status: pending\n" in note
    assert "· Claude (you approved) · Vendor replied" in note
    session = tmp_path / "DEMO-1" / "sessions" / response.json["session"]
    assert session.read_text() == "## Today\nRead the vendor reply.\n"
    assert response.json["session"].endswith(".md") and response.json["session"][:4].isdigit()


def test_apply_without_a_session_note_creates_no_file(tmp_path, claude_client):
    response = apply(claude_client, tmp_path, {**PROPOSAL, "session_note": ""})
    assert response.status_code == 200 and response.json["session"] is None
    assert not (tmp_path / "DEMO-1" / "sessions").exists()


def test_apply_never_overwrites_a_session_file_from_the_same_day(tmp_path, claude_client):
    first = apply(claude_client, tmp_path).json["session"]
    second = apply(claude_client, tmp_path).json["session"]
    assert first != second
    assert len(list((tmp_path / "DEMO-1" / "sessions").iterdir())) == 2


def test_apply_refuses_when_the_note_changed_since_claude_read_it(tmp_path, claude_client):
    note = tmp_path / "DEMO-1" / "note.md"
    before = note.read_text()
    response = apply(claude_client, tmp_path, stamp="old-stamp")
    assert response.status_code == 409 and "ask" in response.json["error"].lower()
    assert note.read_text() == before
    assert not (tmp_path / "DEMO-1" / "sessions").exists()


def test_apply_refuses_priority_and_changes_nothing(tmp_path, claude_client):
    note = tmp_path / "DEMO-1" / "note.md"
    before = note.read_text()
    response = apply(claude_client, tmp_path, {**PROPOSAL, "fields": [{"field": "priority", "value": "critical"}]})
    assert response.status_code == 400 and "priority" in response.json["error"]
    assert note.read_text() == before


def test_apply_with_nothing_to_apply_is_400(tmp_path, claude_client):
    response = apply(claude_client, tmp_path, {"fields": [], "history_line": "", "session_note": ""})
    assert response.status_code == 400


def test_apply_unknown_project_is_404(claude_client):
    response = claude_client.post("/api/projects/NOPE/apply", json={"proposal": PROPOSAL, "stamp": "x"})
    assert response.status_code == 404


# ---------- Slack button: /api/slack ----------

class FakeLive:
    """Stands in for slack_live.Live: a real Inbox, a canned state. Starts no threads."""

    def __init__(self):
        self.inbox = slack_inbox.Inbox()
        self.state = "connected"

    def status(self):
        return {"state": self.state, "message": "", "mode": "instant", **self.inbox.summary(datetime.now())}


def slack_row(channel, ts, kind="mention"):
    return {"kind": kind, "channel": channel, "ts": ts, "tags": ["@you"], "thread": None, "who": "Mike",
            "where": "#ops", "convo": "Mike", "text": "hi", "link": f"slack://channel?team=T0&id={channel}&message={ts}"}


@pytest.fixture
def live():
    return FakeLive()


@pytest.fixture
def slack_client(tmp_path, live):
    app = create_app(tmp_path, slack=live)
    app.config.update(TESTING=True)
    return app.test_client()


def test_slack_status_comes_from_the_live_part(slack_client, live):
    live.inbox.add(slack_row("C0OPS", "1792541580.212069"))
    got = slack_client.get("/api/slack").json
    assert got["state"] == "connected" and got["count"] == 1 and got["mentions"][0]["who"] == "Mike"


def test_slack_off_when_the_app_has_no_slack_part(client):
    got = client.get("/api/slack").json
    assert got["state"] == "off" and "SLACK_USER_TOKEN" in got["message"]
    assert got["count"] == 0 and got["mentions"] == [] and got["dms"] == []


def test_opening_a_row_clears_it_at_once(slack_client, live):
    live.inbox.add(slack_row("C0OPS", "1792541580.212069"))
    live.inbox.add(slack_row("C0OPS", "1792541590.000100"))
    got = slack_client.post("/api/slack/opened", json={"channel": "C0OPS", "ts": "1792541580.212069"}).json
    assert got["count"] == 1 and got["mentions"][0]["ts"] == "1792541590.000100"


def test_opening_needs_a_channel_and_ts(slack_client):
    assert slack_client.post("/api/slack/opened", json={"channel": "C0OPS"}).status_code == 400
    assert slack_client.post("/api/slack/opened", json={"channel": 5, "ts": "1.2"}).status_code == 400


def test_opening_from_another_website_is_refused(slack_client, live):
    live.inbox.add(slack_row("C0OPS", "1792541580.212069"))
    evil = slack_client.post("/api/slack/opened", json={"channel": "C0OPS", "ts": "1792541580.212069"},
                             headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403 and live.inbox.summary(datetime.now())["count"] == 1


def test_real_run_starts_slack_with_the_settings_ini_lines(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(app_module, "load_settings",
                        lambda: {"projects_folder": str(tmp_path), "slack_poll_seconds": "45"})
    monkeypatch.setattr(app_module.slack_live, "start",
                        lambda settings, inbox: started.append(settings) or FakeLive())
    create_app()
    assert len(started) == 1 and started[0]["poll_seconds"] == 45 and started[0]["mode"] == "instant"


def test_real_run_with_a_bad_setting_stops_before_slack_starts(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(app_module, "load_settings",
                        lambda: {"projects_folder": str(tmp_path), "text_limit": "lots"})
    monkeypatch.setattr(app_module.slack_live, "start",
                        lambda settings, inbox: started.append(settings) or FakeLive())
    with pytest.raises(SystemExit):
        create_app()
    assert started == []        # no Slack threads left running behind the error message
