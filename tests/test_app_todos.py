"""The To do page's routes: /api/todos (app.py over todos.py)."""
from pathlib import Path

import pytest

import todos
from app import LOCKED, UNREADABLE, create_app

FILE = """# To do (edited by the Work Assistant To do page)

- [ ] tidy the test folder
- [x] send the weekly report
- [ ] (high) call the vendor back
"""
ODD = "The page sent something odd. Reload the page (F5) and try again."


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path)
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def folder(tmp_path):
    (tmp_path / todos.TODO_FILE).write_text(FILE, encoding="utf-8")
    return tmp_path


def file_text(folder):
    return (folder / todos.TODO_FILE).read_text(encoding="utf-8")


def texts(response):
    return [t["text"] for t in response.json["todos"]]


# ---------- GET ----------

def test_get_with_no_file_is_an_empty_list(client):
    assert client.get("/api/todos").json == {"todos": [], "open": 0, "open_high": 0, "done": 0}


def test_get_gives_the_listing(folder, client):
    response = client.get("/api/todos")
    assert response.json == todos.listing(todos.parse(FILE))
    assert texts(response) == ["call the vendor back", "tidy the test folder", "send the weekly report"]


def test_todos_md_is_not_a_project(folder, client):
    assert client.get("/api/projects").json["projects"] == []


# ---------- happy paths: each returns the fresh list ----------

def test_add(tmp_path, client):
    response = client.post("/api/todos", json={"text": "  ring the NOC "})
    assert response.status_code == 200
    assert texts(response) == ["ring the NOC"]
    assert file_text(tmp_path) == todos.HEADER + "\n\n- [ ] ring the NOC\n"


def test_done(folder, client):
    response = client.post("/api/todos/done", json={"row": 0, "text": "tidy the test folder", "done": True})
    assert response.status_code == 200
    assert response.json["done"] == 2
    assert todos.read_todos(folder)[0]["done"] is True


def test_high(folder, client):
    response = client.post("/api/todos/high", json={"row": 2, "text": "call the vendor back", "high": False})
    assert response.status_code == 200
    assert response.json["open_high"] == 0
    assert todos.read_todos(folder)[2]["high"] is False


def test_text(folder, client):
    response = client.post("/api/todos/text", json={"row": 1, "text": "send the weekly report",
                                                    "new_text": "send the monthly report"})
    assert response.status_code == 200
    assert "send the monthly report" in texts(response)


def test_delete(folder, client):
    response = client.post("/api/todos/delete", json={"row": 0, "text": "tidy the test folder"})
    assert response.status_code == 200
    assert texts(response) == ["call the vendor back", "send the weekly report"]


def test_clear_done(folder, client):
    response = client.post("/api/todos/clear-done", json={"texts": ["send the weekly report"]})
    assert response.status_code == 200
    assert texts(response) == ["call the vendor back", "tidy the test folder"]


def test_line_breaks_in_a_new_todo_become_spaces(tmp_path, client):
    response = client.post("/api/todos", json={"text": "pasted\x0bfrom\u2028Excel"})
    assert response.status_code == 200
    assert texts(response) == ["pasted from Excel"]


@pytest.mark.parametrize("url, body", [
    ("/api/todos", {"text": "new one"}),
    ("/api/todos/done", {"row": 0, "text": "tidy the test folder", "done": True}),
    ("/api/todos/clear-done", {"texts": ["send the weekly report"]}),
])
def test_a_change_reads_the_file_once(folder, client, monkeypatch, url, body):
    reads = []
    real_read = todos.read_todos
    monkeypatch.setattr(todos, "read_todos", lambda f: reads.append(f) or real_read(f))
    assert client.post(url, json=body).status_code == 200
    assert len(reads) == 1


def test_the_page_gets_the_empty_message_and_the_length_limit_from_todos_py(client):
    page = client.get("/").get_data(as_text=True)
    assert todos.EMPTY in page
    assert f'id="todo-new" maxlength="{todos.MAX_LENGTH}"' in page
    assert f'data-max-length="{todos.MAX_LENGTH}"' in page
    js = (Path(__file__).parent.parent / "static" / "todo.js").read_text(encoding="utf-8")
    assert todos.EMPTY not in js and 'maxlength="500"' not in js       # one copy only: todos.py


def test_a_broken_character_is_saved_as_a_question_mark(folder, client):
    response = client.post("/api/todos", json={"text": "bad \ud800 paste"})
    assert response.status_code == 200
    assert "bad ? paste" in texts(response)


def test_an_unexpected_error_is_not_shown_as_a_todo_message(folder, client, monkeypatch):
    def broken(*args):
        raise ValueError("'utf-8' codec can't encode character")     # technical words, not for the page
    monkeypatch.setattr(todos, "add", broken)
    with pytest.raises(ValueError):          # TESTING=True: Flask hands it to us instead of a plain 500 page
        client.post("/api/todos", json={"text": "new one"})


def test_no_projects_folder_says_how_to_fix_it(tmp_path):
    client = create_app(tmp_path / "gone").test_client()
    for response in [client.get("/api/todos"), client.post("/api/todos", json={"text": "new one"})]:
        assert response.status_code == 400
        assert response.json["error"] == todos.NO_FOLDER.format(tmp_path / "gone")


# ---------- errors ----------

@pytest.mark.parametrize("url, body", [
    ("/api/todos", {"text": "   "}),
    ("/api/todos", {"text": "x" * (todos.MAX_LENGTH + 1)}),
    ("/api/todos/text", {"row": 0, "text": "tidy the test folder", "new_text": "(high) sneaky"}),
])
def test_bad_text_is_400_with_the_message(folder, client, url, body):
    response = client.post(url, json=body)
    assert response.status_code == 400
    assert response.json["error"] in (todos.EMPTY, todos.TOO_LONG, todos.HIGH_PREFIX)
    assert file_text(folder) == FILE


@pytest.mark.parametrize("url, body", [
    ("/api/todos/done", {"row": 5, "text": "tidy the test folder", "done": True}),
    ("/api/todos/high", {"row": 0, "text": "someone else's words", "high": True}),
    ("/api/todos/text", {"row": -1, "text": "call the vendor back", "new_text": "x"}),
    ("/api/todos/delete", {"row": 1, "text": "tidy the test folder"}),
    ("/api/todos/clear-done", {"texts": []}),
    ("/api/todos/clear-done", {"texts": ["send the weekly report", 3]}),     # can't match the file
])
def test_a_changed_list_is_409(folder, client, url, body):
    response = client.post(url, json=body)
    assert response.status_code == 409
    assert response.json["error"] == todos.CHANGED
    assert file_text(folder) == FILE


@pytest.mark.parametrize("url, body", [
    ("/api/todos", {}),
    ("/api/todos", {"text": 5}),
    ("/api/todos", ["not", "an", "object"]),
    ("/api/todos/done", {"row": "0", "text": "tidy the test folder", "done": True}),
    ("/api/todos/done", {"row": True, "text": "tidy the test folder", "done": True}),
    ("/api/todos/done", {"row": 0.0, "text": "tidy the test folder", "done": True}),
    ("/api/todos/done", {"row": 0, "text": None, "done": True}),
    ("/api/todos/done", {"row": 0, "text": "tidy the test folder", "done": "yes"}),
    ("/api/todos/done", {"row": 0, "text": "tidy the test folder"}),
    ("/api/todos/high", {"row": 0, "text": "tidy the test folder", "high": 1}),
    ("/api/todos/text", {"row": 0, "text": "tidy the test folder"}),
    ("/api/todos/text", {"row": 0, "text": "tidy the test folder", "new_text": 7}),
    ("/api/todos/delete", {"text": "tidy the test folder"}),
    ("/api/todos/delete", "just a string"),
    ("/api/todos/clear-done", {}),
    ("/api/todos/clear-done", {"texts": "send the weekly report"}),
])
def test_an_odd_request_is_400(folder, client, url, body):
    response = client.post(url, json=body)
    assert response.status_code == 400
    assert response.json["error"] == ODD
    assert file_text(folder) == FILE


def test_not_json_at_all_is_400(folder, client):
    response = client.post("/api/todos/delete", data="row=0", content_type="text/plain")
    assert response.status_code == 400
    assert response.json["error"] == ODD


@pytest.mark.parametrize("url, body", [
    ("/api/todos", {"text": "new one"}),
    ("/api/todos/done", {"row": 0, "text": "tidy the test folder", "done": True}),
    ("/api/todos/high", {"row": 0, "text": "tidy the test folder", "high": True}),
    ("/api/todos/text", {"row": 0, "text": "tidy the test folder", "new_text": "x"}),
    ("/api/todos/delete", {"row": 0, "text": "tidy the test folder"}),
    ("/api/todos/clear-done", {"texts": ["send the weekly report"]}),
])
def test_a_locked_file_is_400_with_the_locked_message(folder, client, monkeypatch, url, body):
    def locked(*args, **kwargs):
        raise PermissionError("in use")
    monkeypatch.setattr(Path, "write_bytes", locked)     # todos._write saves with write_bytes
    response = client.post(url, json=body)
    assert response.status_code == 400
    assert response.json["error"] == LOCKED.format("todos.md")
    assert file_text(folder) == FILE


def test_a_post_from_another_website_is_refused(folder, client):
    response = client.post("/api/todos/delete", json={"row": 0, "text": "tidy the test folder"},
                           headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert file_text(folder) == FILE


# ---------- a todos.md the app can't read: plain English, never a crash ----------

@pytest.fixture
def not_utf8(tmp_path):
    (tmp_path / todos.TODO_FILE).write_bytes("- [ ] caf\xe9\n".encode("cp1252"))
    return tmp_path


@pytest.mark.parametrize("method, url, body", [
    ("get", "/api/todos", None),
    ("post", "/api/todos", {"text": "new one"}),
    ("post", "/api/todos/clear-done", {"texts": []}),
])
def test_a_todos_md_not_saved_as_utf8_says_how_to_fix_it(not_utf8, client, method, url, body):
    response = getattr(client, method)(url, json=body)
    assert response.status_code == 400
    assert response.json["error"] == todos.NOT_UTF8
    assert (not_utf8 / todos.TODO_FILE).read_bytes() == "- [ ] caf\xe9\n".encode("cp1252")


def test_a_folder_called_todos_md_says_how_to_fix_it(tmp_path, client):
    (tmp_path / todos.TODO_FILE).mkdir()
    response = client.get("/api/todos")
    assert response.status_code == 400
    assert response.json["error"] == todos.NOT_A_FILE


def test_a_todos_md_that_cannot_be_read_says_so(folder, client, monkeypatch):
    def locked(*args, **kwargs):
        raise PermissionError("in use")
    monkeypatch.setattr(Path, "read_text", locked)
    response = client.get("/api/todos")
    assert response.status_code == 400
    assert response.json["error"] == UNREADABLE.format("todos.md")
