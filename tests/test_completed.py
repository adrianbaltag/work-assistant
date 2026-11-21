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
    projects, work = tmp_path / "home" / "projects", tmp_path / "home" / "work_jira"
    projects.mkdir(parents=True)
    work.mkdir()
    return projects, work


@pytest.fixture
def client(folders):
    projects, work = folders
    app = create_app(projects, work_jira_folder=str(work), home=projects.parent)
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


def complete(client, folders, name):
    """✓ Complete with the one-time box answered: PROD_SCRIPTS in the (fake) Documents folder."""
    return client.post(f"/api/projects/{name}/complete", json={"prod_folder": str(prod(folders))})


def prod(folders):
    return folders[0].parent / "Documents" / "PROD_SCRIPTS"


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
    assert complete(client, folders, "ABC-5").status_code == 200


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

    assert complete(client, folders, "ABC-1").status_code == 200

    [done] = client.get("/api/projects").json["completed"]
    assert done["ended"] == "Ticket closed"
    assert not (work / "ABC-1").exists() and (prod(folders) / "ABC-1").is_dir()     # G3: the folder moves too


def test_a_completed_ticket_card_does_not_come_back_on_the_next_import(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")

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
    assert complete(client, folders, "ABC-3").status_code == 200
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


# ---------- G3: the ticket folder moves to PROD_SCRIPTS and back ----------

import notes            # noqa: E402  (G3 tests only)
import prod_folder      # noqa: E402


def fields(folder):
    return notes.parse_note((folder / "note.md").read_text(encoding="utf-8"))[0]


def test_where_the_folder_goes_is_found_by_its_tag_or_suggested(folders, client):
    assert client.get("/api/prod-folder").json == {"folder": None, "suggest": str(prod(folders))}
    target = folders[0].parent / "Desktop" / "Done stuff"
    prod_folder.make(target)
    assert client.get("/api/prod-folder").json == {"folder": str(target), "suggest": str(prod(folders))}


def test_complete_moves_the_ticket_folder_and_the_card_remembers_where(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))

    response = complete(client, folders, "ABC-1")

    assert response.status_code == 200
    moved = prod(folders) / "ABC-1"
    assert (moved / "requirements.md").is_file() and (prod(folders) / prod_folder.TAG).is_file()
    archived = projects / "_archive" / "ABC-1"
    assert fields(archived)["prod_folder"] == str(moved.resolve())
    assert fields(archived)["folder"] == str(work / "ABC-1")              # where Restore puts it back


def test_complete_with_no_box_answer_uses_the_tagged_folder(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    prod_folder.make(prod(folders))

    assert client.post("/api/projects/ABC-1/complete").status_code == 200
    assert (prod(folders) / "ABC-1").is_dir()


def test_complete_with_no_box_answer_and_no_tag_asks_and_moves_nothing(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))

    response = client.post("/api/projects/ABC-1/complete")

    assert response.status_code == 400 and response.json["need_folder"] is True
    assert response.json["suggest"] == str(prod(folders))
    assert (work / "ABC-1").is_dir() and "ABC-1" in rows(client)


def test_a_bad_box_answer_is_refused_and_moves_nothing(folders, client, tmp_path):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    for typed in (str(tmp_path / "outside"), str(work / "PROD"), "PROD_SCRIPTS"):
        response = client.post("/api/projects/ABC-1/complete", json={"prod_folder": typed})
        assert response.status_code == 400 and response.json["error"]
    assert (work / "ABC-1").is_dir() and "ABC-1" in rows(client)
    assert not (tmp_path / "outside").exists()


def test_a_taken_name_in_prod_scripts_gets_the_date_and_the_card_remembers_it(folders, client):
    projects, work = folders
    (prod(folders) / "ABC-1").mkdir(parents=True)                           # an older ABC-1 already there
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))

    assert complete(client, folders, "ABC-1").status_code == 200

    [moved] = [f for f in prod(folders).iterdir() if f.name.startswith("ABC-1 (")]
    assert fields(projects / "_archive" / "ABC-1")["prod_folder"] == str(moved.resolve())
    assert (prod(folders) / "ABC-1").is_dir()                               # the older one is untouched


def test_a_locked_ticket_folder_moves_nothing_and_says_close_the_program(folders, client, monkeypatch):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    def locked(*args):
        raise PermissionError(13, "Access is denied", str(work / "ABC-1"))
    monkeypatch.setattr(prod_folder, "move_out", locked)

    response = complete(client, folders, "ABC-1")

    assert response.status_code == 400
    assert response.json["error"] == app_module.FOLDER_LOCKED.format("ABC-1")
    assert (work / "ABC-1").is_dir() and "ABC-1" in rows(client)


def test_prod_scripts_on_another_drive_says_so(folders, client, monkeypatch):
    import errno
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    def far(*args):
        raise OSError(errno.EXDEV, "Invalid cross-device link")
    monkeypatch.setattr(prod_folder, "move_out", far)

    response = complete(client, folders, "ABC-1")

    assert response.status_code == 400
    assert response.json["error"] == app_module.OTHER_DRIVE.format("ABC-1", work)


def test_a_card_that_cannot_move_puts_the_ticket_folder_back(folders, client, monkeypatch):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    def locked(*args, **kwargs):
        raise PermissionError(13, "in use")
    monkeypatch.setattr(notes, "archive_project", locked)

    response = complete(client, folders, "ABC-1")

    assert response.status_code == 400
    assert (work / "ABC-1" / "requirements.md").is_file() and not (prod(folders) / "ABC-1").exists()
    assert "ABC-1" in rows(client)


def test_a_plain_card_moves_only_the_card_and_needs_no_box(folders, client):
    projects, _ = folders
    card(projects, "PLAIN")
    assert client.post("/api/projects/PLAIN/complete").status_code == 200
    assert not prod(folders).exists()
    assert "prod_folder" not in fields(projects / "_archive" / "PLAIN")


# ----- Restore -----

def test_restore_moves_the_folder_back_and_says_the_ticket_is_still_closed(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")

    restored = client.post("/api/completed/ABC-1/restore")

    assert restored.json == {"id": "ABC-1", "still_closed": True}
    assert (work / "ABC-1" / "requirements.md").is_file() and not (prod(folders) / "ABC-1").exists()
    back = fields(projects / "ABC-1")
    assert back["prod_folder"] == "" and back["folder"] == str(work / "ABC-1")
    assert rows(client)["ABC-1"]["ready"] == "closed"


def test_restore_of_a_suffixed_folder_puts_it_back_under_its_own_name(folders, client):
    projects, work = folders
    (prod(folders) / "ABC-1").mkdir(parents=True)
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")

    client.post("/api/completed/ABC-1/restore")

    assert (work / "ABC-1" / "requirements.md").is_file()
    assert [f.name for f in prod(folders).iterdir() if not f.name.startswith(".")] == ["ABC-1"]


def test_restore_never_overwrites_a_folder_already_in_work_jira(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    (work / "ABC-1").mkdir()                                                # someone made a new ABC-1

    response = client.post("/api/completed/ABC-1/restore")

    assert response.status_code == 400
    assert response.json["error"] == app_module.RESTORE_CLASH.format("ABC-1", work)
    assert (prod(folders) / "ABC-1" / "requirements.md").is_file() and (projects / "_archive" / "ABC-1").is_dir()


def test_restore_with_the_folder_gone_brings_the_card_back_and_says_so(folders, client):
    import shutil
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    shutil.rmtree(prod(folders) / "ABC-1")

    restored = client.post("/api/completed/ABC-1/restore")

    assert restored.status_code == 200
    assert restored.json["warning"] == app_module.FOLDER_MISSING.format(str((prod(folders) / "ABC-1").resolve()))
    assert "ABC-1" in rows(client) and fields(projects / "ABC-1")["prod_folder"] == ""


def test_restore_with_a_locked_folder_moves_nothing(folders, client, monkeypatch):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    def locked(*args):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(notes.os, "rename", locked)

    response = client.post("/api/completed/ABC-1/restore")

    assert response.status_code == 400
    assert response.json["error"] == app_module.FOLDER_LOCKED.format("ABC-1")
    assert (prod(folders) / "ABC-1").is_dir() and (projects / "_archive" / "ABC-1").is_dir()


def test_restore_puts_the_folder_back_in_prod_scripts_when_the_card_cannot_move(folders, client, monkeypatch):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    def locked(*args, **kwargs):
        raise PermissionError(13, "in use")
    monkeypatch.setattr(notes, "restore_project", locked)

    response = client.post("/api/completed/ABC-1/restore")

    assert response.status_code == 400
    assert (prod(folders) / "ABC-1").is_dir() and not (work / "ABC-1").exists()


def test_restore_with_no_work_jira_setting_moves_nothing_and_says_what_to_fix(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    no_work = create_app(projects, work_jira_folder="", home=projects.parent).test_client()

    restored = no_work.post("/api/completed/ABC-1/restore")

    assert restored.status_code == 400
    assert restored.json["error"] == app_module.NO_WORK_JIRA.format((prod(folders) / "ABC-1").resolve())
    assert (prod(folders) / "ABC-1").is_dir() and (projects / "_archive" / "ABC-1").is_dir()


def test_complete_refuses_a_card_whose_folder_is_not_in_work_jira(folders, client):
    projects, work = folders
    elsewhere = projects.parent / "Documents" / "ABC-1"
    elsewhere.mkdir(parents=True)
    (elsewhere / "requirements.md").write_text(CLOSED, encoding="utf-8")
    card(projects, "ABC-1", linked_to=elsewhere)

    response = complete(client, folders, "ABC-1")

    assert response.status_code == 400
    assert response.json["error"] == app_module.NOT_IN_WORK_JIRA.format("ABC-1", elsewhere, work)
    assert elsewhere.is_dir() and "ABC-1" in rows(client)


def test_restore_of_an_older_closed_card_says_still_closed_but_a_plain_card_does_not(folders, client):
    projects, work = folders
    card(projects, "PLAIN")
    client.post("/api/projects/PLAIN/complete")
    folder = ticket(work, "ABC-9", CLOSED)
    notes.archive_project(projects, card(projects, "ABC-9", linked_to=folder), __import__("datetime").datetime.now())

    assert client.post("/api/completed/PLAIN/restore").json == {"id": "PLAIN"}
    assert client.post("/api/completed/ABC-9/restore").json == {"id": "ABC-9", "still_closed": True}
    assert folder.is_dir()


# ---------- review round 1 ----------

def test_a_box_answer_that_is_not_text_is_refused(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    response = client.post("/api/projects/ABC-1/complete", json={"prod_folder": ["x"]})
    assert response.status_code == 400 and response.json["error"] == app_module.TODO_ODD
    assert (work / "ABC-1").is_dir()


def test_refusals_are_logged(folders, client, caplog):
    import logging
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    with caplog.at_level(logging.WARNING):
        client.post("/api/projects/ABC-1/complete")
        client.post("/api/projects/ABC-1/complete", json={"prod_folder": 5})
    said = [r.getMessage() for r in caplog.records]
    assert any("ABC-1" in m and "no folder for completed projects" in m for m in said)
    assert any("ABC-1" in m and "not text" in m for m in said)


def test_a_folder_that_cannot_be_made_says_so_not_close_the_program(folders, client, monkeypatch):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    def refused(folder):
        raise PermissionError(13, "Access is denied", str(folder))
    monkeypatch.setattr(prod_folder, "make", refused)

    response = complete(client, folders, "ABC-1")

    assert response.status_code == 400
    assert response.json["error"] == app_module.CANT_MAKE.format(prod(folders).resolve(), "Access is denied")
    assert (work / "ABC-1").is_dir()


def test_when_the_folder_cannot_be_put_back_it_says_where_it_is_and_logs_it(folders, client, monkeypatch, caplog):
    import logging
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    def card_locked(*args, **kwargs):
        raise PermissionError(13, "in use")
    monkeypatch.setattr(notes, "archive_project", card_locked)
    real_move = prod_folder.move_out
    def move_then_lock(*args):
        moved = real_move(*args)
        monkeypatch.setattr(app_module.os, "rename", card_locked)       # the move back fails too
        return moved
    monkeypatch.setattr(prod_folder, "move_out", move_then_lock)

    with caplog.at_level(logging.ERROR):
        response = complete(client, folders, "ABC-1")

    moved = (prod(folders) / "ABC-1").resolve()
    assert response.status_code == 400 and response.json["error"] == app_module.STUCK.format("ABC-1", moved)
    assert any("put" in r.getMessage() and "back" in r.getMessage() for r in caplog.records)


def test_the_not_in_work_jira_refusal_says_what_to_do(folders, client):
    words = app_module.NOT_IN_WORK_JIRA.format("ABC-1", "x", "y")
    assert "Move the folder into work_jira" in words and "click ✓ Complete again" in words


def test_restore_with_the_folder_gone_brings_the_card_back_even_with_a_clash_or_no_work_jira(folders, client):
    import shutil
    projects, work = folders
    for name in ("ABC-1", "ABC-2"):
        card(projects, name, linked_to=ticket(work, name, CLOSED))
        complete(client, folders, name)
        shutil.rmtree(prod(folders) / name)
    (work / "ABC-1").mkdir()                                                # a new ABC-1 in work_jira
    no_work = create_app(projects, work_jira_folder="", home=projects.parent).test_client()

    assert client.post("/api/completed/ABC-1/restore").json["warning"]
    assert no_work.post("/api/completed/ABC-2/restore").json["warning"]
    assert {"ABC-1", "ABC-2"} <= set(rows(client))


def test_restore_never_moves_a_folder_outside_the_allowed_places(folders, client, tmp_path):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    important = tmp_path / "Important"
    important.mkdir()
    note = projects / "_archive" / "ABC-1" / "note.md"
    note.write_text(notes.set_fields(note.read_text(encoding="utf-8"), {"prod_folder": str(important)}),
                    encoding="utf-8")

    response = client.post("/api/completed/ABC-1/restore")

    assert response.status_code == 400
    assert response.json["error"] == app_module.ODD_PROD_FOLDER.format(important)
    assert important.is_dir() and not (work / "ABC-1").exists()


def test_a_folder_name_with_two_spaces_goes_out_and_comes_back(folders, client):
    projects, work = folders
    card(projects, "ABC-1  hotfix", linked_to=ticket(work, "ABC-1  hotfix", CLOSED))

    assert complete(client, folders, "ABC-1  hotfix").status_code == 200
    assert (prod(folders) / "ABC-1 hotfix").is_dir()
    assert client.post("/api/completed/ABC-1  hotfix/restore").json.get("warning") is None
    assert (work / "ABC-1  hotfix" / "requirements.md").is_file()


def test_other_drive_message_says_to_pick_a_folder_on_work_jiras_drive():
    words = app_module.OTHER_DRIVE.format("ABC-1", r"D:\work_jira")
    assert "same drive as D:\\work_jira" in words


# ---------- review round 2 ----------

def test_restore_never_moves_a_folder_that_is_not_in_a_tagged_folder(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    important = projects.parent / "Documents" / "Important"                # inside home, but no tag next to it
    important.mkdir()
    note = projects / "_archive" / "ABC-1" / "note.md"
    note.write_text(notes.set_fields(note.read_text(encoding="utf-8"), {"prod_folder": str(important)}),
                    encoding="utf-8")

    response = client.post("/api/completed/ABC-1/restore")

    assert response.status_code == 400
    assert response.json["error"] == app_module.ODD_PROD_FOLDER.format(important)
    assert important.is_dir() and not (work / "ABC-1").exists()


def test_two_spaces_round_trip_keeps_the_cards_folder_line(folders, client):
    projects, work = folders
    card(projects, "ABC-1  hotfix", linked_to=ticket(work, "ABC-1  hotfix", CLOSED))
    complete(client, folders, "ABC-1  hotfix")
    client.post("/api/completed/ABC-1  hotfix/restore")
    assert fields(projects / "ABC-1  hotfix")["folder"] == str(work / "ABC-1  hotfix")


def test_restore_finds_the_folder_after_prod_scripts_was_moved(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    moved_to = projects.parent / "Desktop" / "PROD_SCRIPTS"
    moved_to.parent.mkdir()
    prod(folders).rename(moved_to)                                         # you moved PROD_SCRIPTS (tag goes along)

    restored = client.post("/api/completed/ABC-1/restore")

    assert restored.status_code == 200 and "warning" not in restored.json
    assert (work / "ABC-1" / "requirements.md").is_file() and not (moved_to / "ABC-1").exists()


# ---------- review round 3 ----------

def test_restore_never_moves_a_folder_named_with_dot_dot(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    sneaky = f"{prod(folders)}/.."                                         # = Documents itself
    note = projects / "_archive" / "ABC-1" / "note.md"
    note.write_text(notes.set_fields(note.read_text(encoding="utf-8"), {"prod_folder": sneaky}), encoding="utf-8")

    response = client.post("/api/completed/ABC-1/restore")

    # Our own check must refuse it (a Mac refuses to rename ".." anyway, Windows would move Documents)
    assert response.status_code == 400
    assert response.json["error"] == app_module.ODD_PROD_FOLDER.format((projects.parent / "Documents").resolve())
    assert (projects.parent / "Documents" / "PROD_SCRIPTS" / "ABC-1").is_dir()     # Documents did not move
    assert not (work / "ABC-1").exists()


def test_restore_after_work_jira_moved_points_the_card_at_the_new_place(folders, client):
    projects, work = folders
    card(projects, "ABC-1", linked_to=ticket(work, "ABC-1", CLOSED))
    complete(client, folders, "ABC-1")
    new_work = projects.parent / "Desktop" / "work_jira"
    new_work.mkdir(parents=True)
    moved_app = create_app(projects, work_jira_folder=str(new_work), home=projects.parent).test_client()

    assert moved_app.post("/api/completed/ABC-1/restore").status_code == 200

    assert (new_work / "ABC-1" / "requirements.md").is_file()
    assert fields(projects / "ABC-1")["folder"] == str(new_work / "ABC-1")
