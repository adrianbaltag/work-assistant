"""Slice 2: the Flask app serves the dashboard page and the projects as JSON."""
import os
import time

import pytest

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


FORM = {"title": "Fix alarms", "status": "pending", "priority": "high", "next": "call vendor",
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
    assert (row["title"], row["next"], row["blocked_by"]) == ("Fix alarms", "call vendor", "IT")


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
