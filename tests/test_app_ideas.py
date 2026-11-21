"""The Ideas page's routes: /api/ideas (app.py over ideas.py) and + New project started from an idea."""
import time

import pytest

import ideas
from app import LOCKED, create_app

FILE = """# Ideas (edited by the Work Assistant Ideas page)

## 2026-11-21 · Rename old scripts
They all start with tmp_.
Pick one style.

## 2026-11-20 · A quick one
"""
ODD = "The page sent something odd. Reload the page (F5) and try again."


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, home=tmp_path)
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def folder(tmp_path):
    (tmp_path / ideas.IDEA_FILE).write_text(FILE, encoding="utf-8")
    return tmp_path


@pytest.fixture
def work(tmp_path):
    """A projects folder with the ideas file, a work_jira folder, and a client over both."""
    projects = tmp_path / "projects"
    projects.mkdir()
    (tmp_path / "work_jira").mkdir()
    (projects / ideas.IDEA_FILE).write_text(FILE, encoding="utf-8")
    app = create_app(projects, work_jira_folder=str(tmp_path / "work_jira"), home=tmp_path)
    app.config.update(TESTING=True)
    return app.test_client(), projects


# ---------- the list ----------

def test_get_lists_the_ideas_newest_first_with_rows(client, folder):
    found = client.get("/api/ideas").json
    assert found["count"] == 2
    assert [(i["row"], i["name"], i["date"]) for i in found["ideas"]] == [
        (0, "Rename old scripts", "2026-11-21"), (1, "A quick one", "2026-11-20")]


def test_get_with_no_file_yet_is_an_empty_list(client):
    assert client.get("/api/ideas").json == {"ideas": [], "count": 0}


def test_get_a_file_that_is_not_utf8_says_how_to_fix(client, tmp_path):
    (tmp_path / ideas.IDEA_FILE).write_bytes("## caf\xe9\n".encode("latin-1"))
    response = client.get("/api/ideas")
    assert response.status_code == 400 and "UTF-8" in response.json["error"]


def test_add_saves_with_today_and_answers_with_the_new_list(client, folder):
    response = client.post("/api/ideas", json={"text": "New one\ndetail"})
    first = response.json["ideas"][0]
    assert (first["name"], first["details"], first["date"]) == ("New one", "detail", time.strftime("%Y-%m-%d"))
    assert response.json["count"] == 3


def test_add_empty_text_says_type_an_idea(client):
    response = client.post("/api/ideas", json={"text": "  \n "})
    assert response.status_code == 400 and response.json["error"] == ideas.EMPTY


@pytest.mark.parametrize("body", [{}, {"text": 5}, [1], None])
def test_add_with_an_odd_body_says_reload(client, body):
    response = client.post("/api/ideas", json=body)
    assert response.status_code == 400 and response.json["error"] == ODD


def test_delete_removes_it_and_answers_with_the_new_list(client, folder):
    response = client.post("/api/ideas/delete", json={"row": 0, "name": "Rename old scripts"})
    assert [i["name"] for i in response.json["ideas"]] == ["A quick one"]


def test_delete_a_stale_row_answers_409_and_changes_nothing(client, folder):
    response = client.post("/api/ideas/delete", json={"row": 0, "name": "A quick one"})
    assert response.status_code == 409 and response.json["error"] == ideas.CHANGED
    assert ideas.read_ideas(folder) == ideas.parse(FILE)


@pytest.mark.parametrize("body", [{"row": "0", "name": "Rename old scripts"}, {"row": True, "name": "x"},
                                  {"row": 0}, {"name": "x"}])
def test_delete_with_an_odd_body_says_reload(client, folder, body):
    response = client.post("/api/ideas/delete", json=body)
    assert response.status_code == 400 and response.json["error"] == ODD


def test_a_locked_file_says_close_it(client, folder, monkeypatch):
    def locked(*_):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(ideas, "_write", locked)
    response = client.post("/api/ideas", json={"text": "New"})
    assert response.status_code == 400 and response.json["error"] == LOCKED.format(ideas.IDEA_FILE)


# ---------- Start as project ----------

def test_start_as_personal_project_puts_the_details_in_the_goal_and_removes_the_idea(client, folder):
    response = client.post("/api/projects", json={"id": "rename_scripts", "title": "Rename old scripts",
                                                  "status": "active", "idea": {"row": 0, "name": "Rename old scripts"}})
    assert response.json == {"id": "rename_scripts"}
    text = client.get("/api/projects/rename_scripts").json["text"]
    assert "## Goal\nThey all start with tmp_.\nPick one style.\n" in text
    assert [i["name"] for i in ideas.read_ideas(folder)] == ["A quick one"]


def test_start_as_work_project_puts_the_edited_description_in_the_goal(work):
    client, projects = work
    response = client.post("/api/projects", json={"id": "ABC-123", "title": "Rename old scripts", "status": "active",
                                                  "work": True, "description": "Edited in the form.",
                                                  "idea": {"row": 0, "name": "Rename old scripts"}})
    assert response.json == {"id": "ABC-123"}
    text = client.get("/api/projects/ABC-123").json["text"]
    assert "## Goal\nEdited in the form.\n" in text          # what you typed in the form wins (decided: A)
    assert [i["name"] for i in ideas.read_ideas(projects)] == ["A quick one"]


def test_start_an_idea_with_no_details_leaves_the_goal_empty(client, folder):
    client.post("/api/projects", json={"id": "quick", "status": "active", "idea": {"row": 1, "name": "A quick one"}})
    assert "## Goal\n\n" in client.get("/api/projects/quick").json["text"]
    assert [i["name"] for i in ideas.read_ideas(folder)] == ["Rename old scripts"]


def test_start_a_stale_idea_makes_no_project(client, folder):
    response = client.post("/api/projects", json={"id": "x1", "status": "active",
                                                  "idea": {"row": 0, "name": "A quick one"}})
    assert response.status_code == 409 and response.json["error"] == ideas.STALE_IDEA
    assert not (folder / "x1").exists()
    assert ideas.read_ideas(folder) == ideas.parse(FILE)


def test_a_failed_create_keeps_the_idea(client, folder):
    (folder / "taken").mkdir()
    response = client.post("/api/projects", json={"id": "taken", "status": "active",
                                                  "idea": {"row": 0, "name": "Rename old scripts"}})
    assert response.status_code == 400
    assert ideas.read_ideas(folder) == ideas.parse(FILE)


def test_an_idea_that_cannot_be_removed_after_create_says_delete_it_by_hand(client, folder, monkeypatch):
    def locked(*_):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(ideas, "_write", locked)
    response = client.post("/api/projects", json={"id": "made", "status": "active",
                                                  "idea": {"row": 0, "name": "Rename old scripts"}})
    assert response.json["id"] == "made"
    assert "Delete it on the Ideas page" in response.json["note"]
    assert (folder / "made" / "note.md").is_file()


@pytest.mark.parametrize("idea", [{"row": "0", "name": "x"}, {"row": 0}, "Rename old scripts", 3])
def test_start_with_an_odd_idea_says_reload_and_makes_nothing(client, folder, idea):
    response = client.post("/api/projects", json={"id": "odd", "status": "active", "idea": idea})
    assert response.status_code == 400 and response.json["error"] == ODD
    assert not (folder / "odd").exists()


def test_the_new_project_form_no_longer_offers_idea_as_a_status(client):
    response = client.post("/api/projects", json={"id": "x2", "status": "idea"})
    assert response.status_code == 400


HASH_FILE = "# Ideas\n\n## 2026-11-21 · Odd lines\nfirst\n ## History\n# big\nlast\n"


def test_hash_lines_in_the_details_stay_inside_the_goal_and_history_still_works(client, tmp_path):
    (tmp_path / ideas.IDEA_FILE).write_text(HASH_FILE, encoding="utf-8")
    client.post("/api/projects", json={"id": "odd", "status": "active", "idea": {"row": 0, "name": "Odd lines"}})
    card = client.get("/api/projects/odd").json
    assert "## Goal\nfirst\n\\## History\n\\# big\nlast\n" in card["text"]
    assert [line.strip() for line in card["text"].splitlines()].count("## History") == 1
    assert card["history"] == []


def test_hash_lines_in_an_edited_work_description_stay_inside_the_goal(work):
    client, projects = work
    client.post("/api/projects", json={"id": "ABC-124", "status": "active", "work": True,
                                       "description": "## History\nfix", "idea": {"row": 1, "name": "A quick one"}})
    assert "## Goal\n\\## History\nfix\n" in client.get("/api/projects/ABC-124").json["text"]


def test_a_failed_work_folder_keeps_the_idea(work, monkeypatch):
    client, projects = work
    def broken(*_):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr("project_note.start_work_folder", broken)
    response = client.post("/api/projects", json={"id": "ABC-125", "status": "active", "work": True,
                                                  "idea": {"row": 0, "name": "Rename old scripts"}})
    assert response.status_code == 400
    assert ideas.read_ideas(projects) == ideas.parse(FILE)


def test_a_goal_that_cannot_be_written_says_copy_them_by_hand_and_still_removes_the_idea(client, folder, monkeypatch):
    import notes
    real = notes.safe_write
    def picky(path, text):
        if "They all start with tmp_." in text:
            raise PermissionError(13, "Permission denied")
        return real(path, text)
    monkeypatch.setattr(notes, "safe_write", picky)
    response = client.post("/api/projects", json={"id": "made2", "status": "active",
                                                  "idea": {"row": 0, "name": "Rename old scripts"}})
    assert response.json["id"] == "made2"
    assert "copy them in by hand" in response.json["note"]
    assert [i["name"] for i in ideas.read_ideas(folder)] == ["A quick one"]


def test_an_unreadable_ideas_file_is_written_to_the_log(client, tmp_path, caplog):
    (tmp_path / ideas.IDEA_FILE).write_bytes("## caf\xe9\n".encode("latin-1"))
    client.get("/api/ideas")
    client.post("/api/ideas", json={"text": "x"})
    client.post("/api/projects", json={"id": "y", "status": "active", "idea": {"row": 0, "name": "x"}})
    assert sum(ideas.IDEA_FILE in r.getMessage() for r in caplog.records) == 3
