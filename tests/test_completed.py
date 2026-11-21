"""G2: the Completed tab. Each dashboard row says if it can be completed; Complete moves the card to
_archive (the folder name on disk stays); the Completed list and Restore. Made-up IDs only."""
import pytest

import app as app_module
import project_note
from app import create_app

CLOSED = "**Status:** CONFIRMED BY CREATOR (2026-11-01)\n\n## Closed\n\nDone, creator said yes.\n"
OPEN = "**Status:** CONFIRMED BY CREATOR (2026-11-01)\n\n## Milestones\n\n- [ ] M1: build it\n"


@pytest.fixture
def folders(tmp_path):
    projects, work = tmp_path / "projects", tmp_path / "work_jira"
    projects.mkdir()
    work.mkdir()
    return projects, work


@pytest.fixture
def client(folders):
    projects, work = folders
    app = create_app(projects, work_jira_folder=str(work))
    app.config.update(TESTING=True)
    return app.test_client()


def card(projects, name, title="", linked_to=None, history=""):
    """A card (projects/<name>/note.md). linked_to = its work folder (source: work_jira)."""
    folder = projects / name
    folder.mkdir()
    link = f"source: work_jira\nfolder: {linked_to}\n" if linked_to else ""
    (folder / "note.md").write_text(f"---\ntitle: {title or name}\nstatus: active\npriority: normal\n"
                                    f"jira: {name}\n{link}---\n\n## History\n{history}", encoding="utf-8")
    return folder


def ticket(work, name, requirements=None):
    """A work folder with a tracking_log.md (so the sync is happy) and maybe a requirements.md."""
    folder = work / name
    folder.mkdir()
    (folder / "tracking_log.md").write_text("## Now working on\n\n## Next up\n\n## Last update\n", encoding="utf-8")
    if requirements is not None:
        (folder / "requirements.md").write_text(requirements, encoding="utf-8")
    return folder


def rows(client):
    return {r["id"]: r for r in client.get("/api/projects").json["projects"]}


# ---------- which rows can be completed ----------

def test_each_row_says_if_it_can_be_completed_and_why(folders, client):
    projects, work = folders
    card(projects, "PLAIN")
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    card(projects, "ABC-2", linked_to=ticket(work, "ABC-2", OPEN))
    card(projects, "ABC-3", linked_to=ticket(work, "ABC-3"))                 # no requirements.md yet
    card(projects, "ABC-4", linked_to=work / "ABC-4")                       # folder away (VPN off)

    got = {name: r["ready"] for name, r in rows(client).items()}

    assert got == {"PLAIN": "no_ticket", "ABC-1": "closed", "ABC-2": "",
                   "ABC-3": "no_requirements", "ABC-4": "away"}


OLD_TICKET = "# ABC-5\n\n- Status: only open alarms\n\n## Milestones\n\n- [ ] M1: build it\n"     # before ticket-flow
WAITING_CLOSED = "**Status:** WAITING FOR CREATOR (2026-11-01)\n\n## Closed\n\nDropped.\n"


def test_closed_heading_counts_in_any_ticket_and_an_old_ticket_is_yours_to_decide(folders, client):
    projects, work = folders
    card(projects, "ABC-5", linked_to=ticket(work, "ABC-5", OLD_TICKET))
    card(projects, "ABC-6", linked_to=ticket(work, "ABC-6", OLD_TICKET + "\n## Closed\n\nDone.\n"))
    card(projects, "ABC-7", linked_to=ticket(work, "ABC-7", WAITING_CLOSED))
    card(projects, "ABC-8", linked_to=ticket(work, "ABC-8", OPEN + "\n<!-- ## Closed -->\n"))   # a comment is not a close

    got = {name: r["ready"] for name, r in rows(client).items()}

    assert got == {"ABC-5": "old_ticket", "ABC-6": "closed", "ABC-7": "closed", "ABC-8": ""}
    assert client.post("/api/projects/ABC-5/complete").status_code == 200


def test_a_requirements_file_that_cannot_be_read_greys_one_row_and_the_rest_still_show(folders, client, monkeypatch,
                                                                                        caplog):
    import logging
    projects, work = folders
    card(projects, "PLAIN")
    card(projects, "ABC-2", linked_to=ticket(work, "ABC-2", OPEN))
    real = project_note.requirements_text
    def locked(work_folder):
        if str(work_folder).endswith("ABC-2"):
            raise PermissionError(13, "Permission denied", str(work_folder))
        return real(work_folder)
    monkeypatch.setattr(project_note, "requirements_text", locked)

    with caplog.at_level(logging.WARNING):
        response = client.get("/api/projects")

    assert response.status_code == 200
    assert {r["id"]: r["ready"] for r in response.json["projects"]} == {"PLAIN": "no_ticket", "ABC-2": "unreadable"}
    assert any("ABC-2" in r.getMessage() and "requirements.md" in r.getMessage() for r in caplog.records)   # logged
    refused = client.post("/api/projects/ABC-2/complete")
    assert refused.status_code == 400 and refused.json["error"] == app_module.TICKET_UNREADABLE.format("ABC-2")


# ---------- Complete ----------

def test_complete_a_plain_card_moves_it_to_completed(folders, client):
    projects, _ = folders
    card(projects, "PLAIN", title="Side job")

    assert client.post("/api/projects/PLAIN/complete").status_code == 200

    data = client.get("/api/projects").json
    assert data["projects"] == []
    [done] = data["completed"]
    assert (done["id"], done["title"], done["ended"]) == ("PLAIN", "Side job", "Completed")
    assert done["finished"]                                                  # a date, YYYY-MM-DD
    assert "body" not in done
    assert (projects / "_archive" / "PLAIN" / "note.md").is_file()          # the folder on disk keeps its name


def test_complete_a_closed_ticket_says_ticket_closed(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))

    assert client.post("/api/projects/ABC-1/complete").status_code == 200

    [done] = client.get("/api/projects").json["completed"]
    assert done["ended"] == "Ticket closed"
    assert (work / "ABC-1").is_dir()                                         # G2 moves the card only


def test_a_completed_ticket_card_does_not_come_back_on_the_next_import(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    client.post("/api/projects/ABC-1/complete")

    assert project_note.import_missing(projects, work, __import__("datetime").datetime.now()) == []
    assert rows(client) == {}


@pytest.mark.parametrize("name, requirements, words", [("ABC-2", OPEN, app_module.NOT_CLOSED),
                                                       ("ABC-4", None, app_module.FOLDER_AWAY)])
def test_an_open_or_unreachable_ticket_cannot_be_completed(folders, client, name, requirements, words):
    projects, work = folders
    folder = ticket(work, name, requirements) if requirements else work / name
    card(projects, name, linked_to=folder)

    response = client.post(f"/api/projects/{name}/complete")

    assert response.status_code == 400
    assert response.json["error"] == words.format(name)
    assert name in rows(client)


def test_complete_of_a_card_with_no_requirements_file_works(folders, client):
    projects, work = folders
    card(projects, "ABC-3", linked_to=ticket(work, "ABC-3"))
    assert client.post("/api/projects/ABC-3/complete").status_code == 200
    assert client.get("/api/projects").json["completed"][0]["ended"] == "Completed"


def test_complete_unknown_card_is_404_and_old_archive_routes_are_gone(folders, client):
    projects, _ = folders
    card(projects, "PLAIN")
    assert client.post("/api/projects/nope/complete").status_code == 404
    assert client.post("/api/projects/PLAIN/archive").status_code in (404, 405)
    assert client.get("/api/archive").status_code == 404
    assert client.post("/api/archive/files/restore", json={}).status_code in (404, 405)


def test_complete_locked_gives_a_clear_error_and_changes_nothing(folders, client, monkeypatch):
    import notes
    projects, _ = folders
    card(projects, "PLAIN")
    def locked(*args, **kwargs):
        raise PermissionError("in use")
    monkeypatch.setattr(notes.os, "rename", locked)
    response = client.post("/api/projects/PLAIN/complete")
    assert response.status_code == 400 and "open in another program" in response.json["error"]
    assert "PLAIN" in rows(client)


def test_complete_from_another_website_is_refused(folders, client):
    projects, _ = folders
    card(projects, "PLAIN")
    assert client.post("/api/projects/PLAIN/complete", headers={"Origin": "https://evil.example"}).status_code == 403
    assert (projects / "PLAIN" / "note.md").is_file()


def test_complete_on_a_full_disk_says_so_and_logs_it(folders, client, monkeypatch, caplog):
    import logging
    import notes
    projects, _ = folders
    card(projects, "PLAIN")
    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(notes.os, "rename", full)
    with caplog.at_level(logging.ERROR):
        response = client.post("/api/projects/PLAIN/complete")
    assert response.status_code == 400
    assert "No space left on device" in response.json["error"]
    assert "open in another program" not in response.json["error"]      # that would be a wrong guess
    assert any("PLAIN" in r.getMessage() for r in caplog.records)


# ---------- the Completed list ----------

def test_finished_is_the_day_it_was_completed_not_the_newest_file(folders, client):
    projects, _ = folders
    (projects / "_archive").mkdir()
    card(projects / "_archive", "ABC-7", history="- 2026-10-01 · you · Completed\n")
    (projects / "_archive" / "ABC-7" / "raw").mkdir()
    (projects / "_archive" / "ABC-7" / "raw" / "late.txt").write_text("x", encoding="utf-8")
    card(projects / "_archive", "ABC-8")                                       # no event line: note.md's own date
    import os
    os.utime(projects / "_archive" / "ABC-8" / "note.md", (1_700_000_000, 1_700_000_000))   # 2023-11-14

    got = {p["id"]: p["finished"] for p in client.get("/api/projects").json["completed"]}

    assert got == {"ABC-7": "2026-10-01", "ABC-8": "2023-11-14"}


def test_one_unreadable_finished_card_never_blanks_the_dashboard(folders, client, monkeypatch):
    import pathlib
    projects, _ = folders
    card(projects, "OPEN-1")
    (projects / "_archive").mkdir()
    card(projects / "_archive", "ABC-7")
    card(projects / "_archive", "ABC-8")
    real = pathlib.Path.read_text
    def locked(self, *args, **kwargs):
        if self.parent.name == "ABC-7":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, *args, **kwargs)
    monkeypatch.setattr(pathlib.Path, "read_text", locked)

    response = client.get("/api/projects")

    assert response.status_code == 200
    assert [r["id"] for r in response.json["projects"]] == ["OPEN-1"]
    assert [p["id"] for p in response.json["completed"]] == ["ABC-8"]

def test_how_it_ended_for_older_archived_cards(folders, client):
    projects, _ = folders
    (projects / "_archive").mkdir()
    card(projects / "_archive", "ABC-7", history=f"- 2026-10-01 · you · {project_note.MOVED_TO_PROD}\n")
    card(projects / "_archive", "ABC-8", history="- 2026-10-02 · you · Marked done and archived\n")

    got = {p["id"]: p["ended"] for p in client.get("/api/projects").json["completed"]}

    assert got == {"ABC-7": "Moved to prod", "ABC-8": "Marked done"}


def test_completed_list_is_newest_first(folders, client):
    projects, _ = folders
    card(projects, "FIRST")
    card(projects, "SECOND")
    client.post("/api/projects/FIRST/complete")
    import os
    os.utime(projects / "_archive" / "FIRST" / "note.md", (1_700_000_000, 1_700_000_000))   # long ago
    client.post("/api/projects/SECOND/complete")

    assert [p["id"] for p in client.get("/api/projects").json["completed"]] == ["SECOND", "FIRST"]


# ---------- Restore ----------

def test_restore_brings_a_completed_card_back_as_active(folders, client):
    projects, _ = folders
    card(projects, "PLAIN")
    client.post("/api/projects/PLAIN/complete")

    restored = client.post("/api/completed/PLAIN/restore")

    assert restored.json == {"id": "PLAIN"}
    data = client.get("/api/projects").json
    assert [r["id"] for r in data["projects"]] == ["PLAIN"] and data["completed"] == []
    history = [h["text"] for h in client.get("/api/projects/PLAIN").json["history"]]
    assert history[:2] == ["Restored from archive", "Completed"]


def test_restore_unknown_is_404_and_locked_is_a_clear_error(folders, client, monkeypatch):
    import notes
    projects, _ = folders
    card(projects, "PLAIN")
    assert client.post("/api/completed/PLAIN/restore").status_code == 404     # open, not completed
    assert client.post("/api/completed/nope/restore").status_code == 404
    client.post("/api/projects/PLAIN/complete")
    def locked(*args, **kwargs):
        raise PermissionError("in use")
    monkeypatch.setattr(notes.os, "rename", locked)
    response = client.post("/api/completed/PLAIN/restore")
    assert response.status_code == 400 and "open in another program" in response.json["error"]


# ---------- "idea" is out of + New project ----------

def test_new_project_no_longer_takes_idea(client):
    response = client.post("/api/projects", json={"id": "my_idea", "status": "idea"})
    assert response.status_code == 400
    assert client.post("/api/projects", json={"id": "my_job", "status": "pending"}).status_code == 200
