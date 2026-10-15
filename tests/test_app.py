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
