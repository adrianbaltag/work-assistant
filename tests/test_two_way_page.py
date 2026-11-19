"""Two-way, the page's side: Note / Blocker / Unblock sent from a project card.

The user's blocker lives in the card field my_blocker. "Blocked" and the shown status are worked out
each time, never stored. A card that follows a work folder also leaves each message for Claude
(dashboard_inbox). Everything is made up: fake folders (tmp_path), fake names, a fake Claude.
"""
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

import claude_chat
import dashboard_inbox
import notes
import project_note as pn
from app import create_app

NOW = datetime(2026, 11, 18, 9, 30)
TODAY = time.strftime("%Y-%m-%d")
NOTE = "---\ntitle: Demo\nstatus: active\nblocked_by:\n---\nbody text\n\n## History\n- 2026-10-01 · you · first\n"
LOG = "# TEST-101 — Tracking log\n\n## Now working on\n{now}\n\n## Next up\nM3 — email the report\n\n## Last update\n2026-11-17 — M1 ticked\n"
PENDING = "PENDING (Dana, 2026-11-17): waiting for the lab key. M2 — parse the file"


# ---------- notes.dashboard: who blocks a project (worked out, never stored) ----------

def row(**fields):
    return {"id": "A", "status": "active", "priority": "normal", "updated": NOW.timestamp(), **fields}


def shown(**fields):
    return notes.dashboard([row(**fields)], NOW)[0]


def test_no_blocker_means_not_blocked_and_the_status_as_saved():
    p = shown()
    assert (p["blockers"], p["blocked"], p["shown_status"], p["linked"]) == ([], False, "active", False)


def test_my_blocker_blocks_the_project_with_the_label_you():
    p = shown(my_blocker="waiting for Dana")
    assert p["blockers"] == [{"by": "you", "text": "waiting for Dana"}]
    assert p["blocked"] is True and p["shown_status"] == "pending"
    assert p["status"] == "active"                       # the saved status is not touched


def test_a_pending_log_blocks_a_linked_project_with_the_label_log(tmp_path):
    p = shown(source="work_jira", folder=str(tmp_path), status="pending", blocked_by="waiting for the lab key")
    assert p["blockers"] == [{"by": "log", "text": "waiting for the lab key"}]
    assert p["blocked"] is True and p["shown_status"] == "pending" and p["linked"] is True


def test_both_blockers_show_both_labels_and_one_alone_still_blocks(tmp_path):
    linked = {"source": "work_jira", "folder": str(tmp_path)}
    both = shown(**linked, status="pending", blocked_by="lab key", my_blocker="waiting for Dana")
    assert [b["by"] for b in both["blockers"]] == ["you", "log"]
    only_you = shown(**linked, status="active", blocked_by="", my_blocker="waiting for Dana")
    assert only_you["shown_status"] == "pending" and [b["by"] for b in only_you["blockers"]] == ["you"]
    only_log = shown(**linked, status="pending", blocked_by="lab key", my_blocker="")
    assert only_log["shown_status"] == "pending" and [b["by"] for b in only_log["blockers"]] == ["log"]
    neither = shown(**linked, status="active", blocked_by="", my_blocker="")
    assert neither["shown_status"] == "active" and neither["blocked"] is False


def test_a_card_with_no_claude_folder_has_no_log_blocker():
    """Its status and blocked_by are typed by hand on the card: shown as saved, with no label."""
    p = shown(status="pending", blocked_by="typed by hand")
    assert p["blockers"] == [] and p["shown_status"] == "pending" and p["linked"] is False
    info_only = shown(folder="work_jira\\TEST-101")       # folder: alone is just information
    assert info_only["linked"] is False


def test_a_card_stays_linked_while_its_work_folder_is_away(tmp_path):
    p = shown(source="work_jira", folder=str(tmp_path / "gone"), status="pending", blocked_by="lab key")
    assert p["linked"] is True and [b["by"] for b in p["blockers"]] == ["log"]


# ---------- the app: POST /api/projects/<id>/message ----------

URL = "/api/projects/DEMO-1"
LINKED = "/api/projects/TEST-101"


def note_of(projects, project_id="DEMO-1"):
    return (projects / project_id / notes.NOTE_FILE).read_text(encoding="utf-8")


def fields_of(projects, project_id="DEMO-1"):
    return notes.parse_note(note_of(projects, project_id))[0]


def history_of(projects, project_id="DEMO-1"):
    return notes.read_history(note_of(projects, project_id))


def synced_of(projects, project_id="TEST-101"):
    fields = fields_of(projects, project_id)
    return {k: fields.get(k, "") for k in notes.SYNCED_FIELDS}


def row_of(client, project_id):
    return next(p for p in client.get("/api/projects").json["projects"] if p["id"] == project_id)


def inbox_files(folder):
    return sorted((folder / dashboard_inbox.INBOX_DIR).glob("*.json"))


def temp_files(folder):
    return [p.name for p in folder.iterdir() if p.name.endswith(".tmp")]


@pytest.fixture
def projects(tmp_path):
    """The projects folder with DEMO-1: a card with no Claude folder."""
    folder = tmp_path / "projects"
    (folder / "DEMO-1").mkdir(parents=True)
    (folder / "DEMO-1" / notes.NOTE_FILE).write_text(NOTE, encoding="utf-8")
    return folder


@pytest.fixture
def work(tmp_path, projects):
    """work_jira/TEST-101 with a tracking log, and its card TEST-101 that follows it (a linked card)."""
    folder = tmp_path / "work_jira" / "TEST-101"
    folder.mkdir(parents=True)
    (folder / pn.TRACKING_LOG).write_text(LOG.format(now="M2 — parse the file"), encoding="utf-8")
    pn.create(projects, folder, "", "", NOW)
    return folder


@pytest.fixture
def client(tmp_path, projects):
    app = create_app(projects, work_jira_folder=str(tmp_path / "work_jira"))
    app.config.update(TESTING=True)
    return app.test_client()


def send(client, kind, text="", url=URL):
    return client.post(f"{url}/message", json={"kind": kind, "text": text})


def test_a_note_becomes_one_history_line_by_you_and_keeps_the_rest_of_the_note(projects, client):
    response = send(client, "note", "Dana wants  the csv\nby Friday")
    assert response.status_code == 200 and response.json["sent"] is False
    assert history_of(projects)[0] == {"date": TODAY, "who": "you", "text": "Dana wants the csv by Friday"}
    assert history_of(projects)[1]["text"] == "first"
    assert "body text" in note_of(projects) and fields_of(projects)["title"] == "Demo"
    assert temp_files(projects / "DEMO-1") == []


def test_a_note_needs_no_stamp_and_never_says_the_note_changed(projects, client):
    """Someone (Claude Code, an editor) saved note.md after the card was opened: the note still goes in, on top of theirs."""
    client.get(URL)                                               # the card is open
    note = projects / "DEMO-1" / notes.NOTE_FILE
    note.write_text(NOTE.replace("body text", "body text\nadded by someone else"), encoding="utf-8")
    response = send(client, "note", "mine")
    assert response.status_code == 200
    assert "added by someone else" in note_of(projects) and history_of(projects)[0]["text"] == "mine"


def test_the_answer_says_what_the_note_looked_like_before_and_after(projects, client):
    """The page keeps its own "did the note change?" check honest with these two stamps."""
    before = notes.note_stamp(projects / "DEMO-1")
    answer = send(client, "note", "hello").json
    assert answer["before"] == before and answer["stamp"] == notes.note_stamp(projects / "DEMO-1")


def test_a_blocker_sets_my_blocker_and_never_status_or_blocked_by(projects, client):
    response = send(client, "blocker", "waiting for Dana")
    assert response.status_code == 200
    fields = fields_of(projects)
    assert fields["my_blocker"] == "waiting for Dana"
    assert (fields["status"], fields["blocked_by"]) == ("active", "")
    assert history_of(projects)[0] == {"date": TODAY, "who": "you", "text": "Blocker: waiting for Dana"}
    row = row_of(client, "DEMO-1")
    assert row["blocked"] is True and row["shown_status"] == "pending" and row["status"] == "active"
    assert row["blockers"] == [{"by": "you", "text": "waiting for Dana"}]
    assert client.get(URL).json["project"]["blockers"] == row["blockers"]        # the card shows it too


def test_unblock_clears_my_blocker_and_the_project_is_active_again(projects, client):
    send(client, "blocker", "waiting for Dana")
    response = send(client, "unblock")                             # no words needed
    assert response.status_code == 200
    assert fields_of(projects)["my_blocker"] == ""
    assert history_of(projects)[0]["text"] == "Unblocked"
    row = row_of(client, "DEMO-1")
    assert row["blocked"] is False and row["shown_status"] == "active"


def test_unblock_with_words_keeps_them_in_the_history(projects, client):
    send(client, "blocker", "waiting for Dana")
    send(client, "unblock", "Dana sent the key")
    assert history_of(projects)[0]["text"] == "Unblocked: Dana sent the key"


def test_a_second_blocker_replaces_the_reason(projects, client):
    send(client, "blocker", "waiting for Dana")
    send(client, "blocker", "now waiting for the lab")
    assert fields_of(projects)["my_blocker"] == "now waiting for the lab"


def test_unblock_without_a_blocker_is_refused_and_changes_nothing(projects, client):
    before = note_of(projects)
    response = send(client, "unblock")
    assert response.status_code == 400 and "already off" in response.json["error"]
    assert note_of(projects) == before


@pytest.mark.parametrize("kind", ["note", "blocker"])
def test_a_note_or_blocker_with_no_words_is_refused_and_changes_nothing(projects, client, kind):
    before = note_of(projects)
    response = send(client, kind, "  \n ")
    assert response.status_code == 400 and "Type a few words" in response.json["error"]
    assert note_of(projects) == before


@pytest.mark.parametrize("body", [{"kind": "shout", "text": "x"}, {"kind": "note"}, {"text": "x"},
                                  {"kind": "note", "text": 5}, ["note"], "note"])
def test_an_odd_message_body_gives_a_plain_json_error_and_changes_nothing(projects, client, body):
    before = note_of(projects)
    response = client.post(f"{URL}/message", json=body)
    assert response.status_code == 400 and response.is_json and response.json["error"]
    assert note_of(projects) == before


def test_a_message_body_that_is_not_json_gives_a_plain_json_error(projects, client):
    response = client.post(f"{URL}/message", data="not json", content_type="text/plain")
    assert response.status_code == 400 and response.is_json and response.json["error"]


def test_a_message_for_an_unknown_project_is_404(client):
    assert send(client, "note", "x", url="/api/projects/NOPE").status_code == 404


def test_a_message_from_another_website_is_refused(projects, client):
    before = note_of(projects)
    response = client.post(f"{URL}/message", json={"kind": "note", "text": "x"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403 and note_of(projects) == before


def test_a_note_on_a_card_without_a_fields_block_still_goes_in(projects, client):
    (projects / "loose").mkdir()
    (projects / "loose" / notes.NOTE_FILE).write_text("just text\n", encoding="utf-8")
    assert send(client, "note", "first", url="/api/projects/loose").status_code == 200
    assert history_of(projects, "loose")[0]["text"] == "first" and "just text" in note_of(projects, "loose")


def test_a_broken_character_is_refused_and_keeps_the_note(projects, client):
    before = (projects / "DEMO-1" / notes.NOTE_FILE).read_bytes()
    response = send(client, "note", "half an emoji \ud83d")
    assert response.status_code == 400 and "broken character" in response.json["error"]
    assert (projects / "DEMO-1" / notes.NOTE_FILE).read_bytes() == before
    assert temp_files(projects / "DEMO-1") == []


def test_a_locked_note_gives_the_plain_message_and_changes_nothing(projects, client, monkeypatch):
    before = note_of(projects)

    def locked(*args, **kwargs):
        raise PermissionError(13, "in use")
    monkeypatch.setattr(notes.os, "replace", locked)
    response = send(client, "blocker", "waiting for Dana")
    assert response.status_code == 400 and "open in another program" in response.json["error"]
    assert note_of(projects) == before


def test_a_note_that_is_not_utf8_gives_the_plain_message(projects, client):
    (projects / "DEMO-1" / notes.NOTE_FILE).write_bytes("---\ntitle: Café\n---\n".encode("cp1252"))
    response = send(client, "note", "hello")
    assert response.status_code == 400 and "UTF-8" in response.json["error"]


def test_a_save_by_someone_else_at_the_same_moment_is_never_overwritten(projects, client, monkeypatch):
    """note.md changes between our read and our save: we read again and add the line on top of their text."""
    real, calls = notes.write_note, []

    def someone_saves_first(folder, text, stamp, now, force=False):
        if not calls:
            calls.append("x")
            note = folder / notes.NOTE_FILE
            note.write_text(note.read_text(encoding="utf-8").replace("body text", "body text\ntheirs"), encoding="utf-8")
        return real(folder, text, stamp, now, force)
    monkeypatch.setattr(notes, "write_note", someone_saves_first)
    assert send(client, "note", "mine").status_code == 200
    assert "theirs" in note_of(projects) and history_of(projects)[0]["text"] == "mine"
    assert len([h for h in history_of(projects) if h["text"] == "mine"]) == 1


def test_a_note_that_keeps_changing_gives_a_plain_message(projects, client, monkeypatch):
    def always_changed(*args, **kwargs):
        raise notes.StaleNote()
    monkeypatch.setattr(notes, "write_note", always_changed)
    response = send(client, "note", "mine")
    assert response.status_code == 400 and "send it again" in response.json["error"]


# ---------- a linked card: the message is also left for Claude ----------

def test_a_note_on_a_linked_card_is_left_for_claude_with_the_same_words(projects, work, client):
    response = send(client, "note", "Dana wants  the csv\nby Friday", url=LINKED)
    assert response.status_code == 200 and response.json["sent"] is True
    messages = dashboard_inbox.read_all(work)
    assert [(m["kind"], m["text"], m["seen"]) for m in messages] == [("note", "Dana wants the csv by Friday", "")]
    assert history_of(projects, "TEST-101")[0] == {"date": TODAY, "who": "you", "text": "Dana wants the csv by Friday"}


def test_blocker_and_unblock_on_a_linked_card_reach_claude_and_leave_the_synced_fields_alone(projects, work, client):
    before = synced_of(projects)
    send(client, "blocker", "waiting for Dana", url=LINKED)
    assert dashboard_inbox.active_blocker(dashboard_inbox.read_all(work))["text"] == "waiting for Dana"
    assert fields_of(projects, "TEST-101")["my_blocker"] == "waiting for Dana"
    row = row_of(client, "TEST-101")                               # this read also runs the sync
    assert row["blockers"] == [{"by": "you", "text": "waiting for Dana"}] and row["shown_status"] == "pending"
    assert synced_of(projects) == before

    assert send(client, "unblock", url=LINKED).status_code == 200
    messages = dashboard_inbox.read_all(work)
    assert [m["kind"] for m in messages] == ["blocker", "unblock"] and messages[1]["text"] == ""
    assert dashboard_inbox.active_blocker(messages) is None
    assert row_of(client, "TEST-101")["shown_status"] == "active"


def test_both_blockers_on_a_linked_card_and_active_only_when_both_are_gone(projects, work, client):
    (work / pn.TRACKING_LOG).write_text(LOG.format(now=PENDING), encoding="utf-8")
    send(client, "blocker", "waiting for Dana", url=LINKED)
    row = row_of(client, "TEST-101")
    assert row["blockers"] == [{"by": "you", "text": "waiting for Dana"},
                               {"by": "log", "text": "waiting for the lab key."}]
    send(client, "unblock", url=LINKED)
    row = row_of(client, "TEST-101")
    assert [b["by"] for b in row["blockers"]] == ["log"] and row["shown_status"] == "pending"
    (work / pn.TRACKING_LOG).write_text(LOG.format(now="M2 — parse the file, once more"), encoding="utf-8")
    row = row_of(client, "TEST-101")
    assert row["blockers"] == [] and row["shown_status"] == "active"


def test_a_card_with_no_claude_folder_leaves_no_message_file(tmp_path, projects, client):
    info = tmp_path / "info"
    info.mkdir()
    note = projects / "DEMO-1" / notes.NOTE_FILE
    note.write_text(notes.set_fields(NOTE, {"folder": str(info)}), encoding="utf-8")    # folder: alone = information
    response = send(client, "note", "hello")
    assert response.status_code == 200 and response.json["sent"] is False
    assert inbox_files(info) == [] and client.get(URL).json["messages"] is None


def test_work_folder_away_nothing_is_sent_and_nothing_changes(projects, work, client, caplog):
    away = work.with_name("TEST-101-moved")
    work.rename(away)
    before = note_of(projects, "TEST-101")
    response = send(client, "note", "hello", url=LINKED)
    assert response.status_code == 400
    error = response.json["error"]
    assert "Not sent" in error and "work folder" in error and "send it again" in error
    assert note_of(projects, "TEST-101") == before and inbox_files(away) == []
    assert "TEST-101" in caplog.text and "is not there" in caplog.text          # what failed and why, for the terminal


@pytest.mark.parametrize("problem", [OSError(28, "No space left on device"), notes.Locked("x is locked")])
def test_message_file_cannot_be_written_so_the_card_is_put_back_and_the_error_says_so(projects, work, client,
                                                                                    monkeypatch, problem, caplog):
    before = note_of(projects, "TEST-101")

    def fails(*args, **kwargs):
        raise problem
    monkeypatch.setattr(dashboard_inbox, "add", fails)
    response = send(client, "blocker", "waiting for Dana", url=LINKED)
    assert response.status_code == 400
    assert "Not sent" in response.json["error"] and "Nothing was changed" in response.json["error"]
    assert note_of(projects, "TEST-101") == before                 # no half result: no History line, no blocker
    assert temp_files(projects / "TEST-101") == []
    assert "could not be left in" in caplog.text and "waiting for Dana" not in caplog.text    # logged, without your words


def test_message_file_fails_and_the_card_cannot_be_put_back_so_the_error_says_exactly_that(projects, work, client,
                                                                                         monkeypatch, caplog):
    """The worst case: the card is saved, the message file fails, and note.md changed in between so we must not undo."""
    note = projects / "TEST-101" / notes.NOTE_FILE

    def fails_after_someone_saved(*args, **kwargs):
        note.write_text(note.read_text(encoding="utf-8") + "\nsaved by someone else\n", encoding="utf-8")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(dashboard_inbox, "add", fails_after_someone_saved)
    response = send(client, "note", "hello", url=LINKED)
    assert response.status_code == 400
    error = response.json["error"]
    assert "is on the card" in error and "Claude did NOT get it" in error
    assert "saved by someone else" in note_of(projects, "TEST-101")      # their save is never thrown away
    assert history_of(projects, "TEST-101")[0]["text"] == "hello"
    assert "could not be put back" in caplog.text


# ---------- the card: what was sent, and whether Claude has seen it ----------

def test_the_card_lists_the_last_messages_with_waiting_or_seen(projects, work, client):
    assert client.get(LINKED).json["messages"] == []               # linked, nothing sent yet
    for text in ["one", "two", "three", "four"]:
        send(client, "note", text, url=LINKED)
    first_three = [m["id"] for m in dashboard_inbox.read_all(work)][:3]
    dashboard_inbox.mark_seen(work, first_three, NOW)
    shown_messages = client.get(LINKED).json["messages"]
    assert [(m["kind"], m["text"], m["status"]) for m in shown_messages] == [
        ("note", "four", "waiting for Claude"), ("note", "three", "seen by Claude 2026-11-18"),
        ("note", "two", "seen by Claude 2026-11-18")]             # the newest three, newest first


def test_the_card_still_opens_when_the_messages_cannot_be_read(projects, work, client, monkeypatch):
    def fails(*args, **kwargs):
        raise OSError(5, "Input/output error")
    monkeypatch.setattr(dashboard_inbox, "read_all", fails)
    response = client.get(LINKED)
    assert response.status_code == 200 and response.json["messages"] == []


def test_a_broken_message_file_does_not_stop_the_card(projects, work, client):
    send(client, "note", "good one", url=LINKED)
    (work / dashboard_inbox.INBOX_DIR / "20261118-000000-000000-bad.json").write_text("{not json", encoding="utf-8")
    assert [m["text"] for m in client.get(LINKED).json["messages"]] == ["good one"]


# ---------- Save on the card: only the fields the page sends ----------

def save_fields(client, url, fields):
    stamp = client.get(url).json["stamp"]
    return client.post(f"{url}/fields", json={"fields": fields, "stamp": stamp})


def test_save_writes_only_the_fields_it_was_sent(projects, client):
    send(client, "blocker", "waiting for Dana")
    assert save_fields(client, URL, {"jira": "TEST-7"}).status_code == 200
    fields = fields_of(projects)
    assert (fields["jira"], fields["title"], fields["status"]) == ("TEST-7", "Demo", "active")
    assert fields["my_blocker"] == "waiting for Dana"              # Save never touches the user's blocker


def test_save_still_checks_what_it_was_sent(projects, client):
    for bad in [{"title": "  "}, {"status": "done"}, {"priority": "urgent"}]:
        assert save_fields(client, URL, bad).status_code == 400, bad
    assert save_fields(client, URL, {"my_blocker": "sneaked in", "source": "work_jira"}).status_code == 200
    assert "my_blocker" not in fields_of(projects) and "source" not in fields_of(projects)


def test_save_on_a_linked_card_can_never_overwrite_the_synced_values(projects, work, client):
    before = synced_of(projects)
    response = save_fields(client, LINKED, {"title": "New name", "status": "idea", "working_on": "x",
                                            "next": "y", "blocked_by": "z"})
    assert response.status_code == 200
    assert fields_of(projects, "TEST-101")["title"] == "New name"
    assert synced_of(projects) == before


def test_the_card_says_whether_it_is_linked(projects, work, client):
    assert client.get(LINKED).json["project"]["linked"] is True
    assert client.get(URL).json["project"]["linked"] is False


# ---------- Ask Claude on a linked card: never offers the four synced fields ----------

class FakeClaude:
    """Stands in for anthropic.Anthropic(). Remembers the request and gives a canned answer."""

    def __init__(self, proposal=None):
        self.request = None
        self.messages = self
        content = [SimpleNamespace(type="text", text="My update:")]
        if proposal is not None:
            content.append(SimpleNamespace(type="tool_use", id="t1", name="propose_changes", input=proposal))
        self.reply = SimpleNamespace(content=content, stop_reason="tool_use" if proposal else "end_turn")

    def create(self, **request):
        self.request = request
        return self.reply


CONTEXT = [{"type": "text", "text": "the project"}]
EVERY_FIELD = ["title", "status", "working_on", "next", "blocked_by", "tags"]


def offered(fake):
    return fake.request["tools"][0]["input_schema"]["properties"]["fields"]["items"]["properties"]["field"]["enum"]


def proposal_with(field, value="x"):
    return {"fields": [{"field": field, "value": value}], "history_line": "", "session_note": ""}


def test_on_a_linked_card_claude_is_not_offered_the_synced_fields():
    fake = FakeClaude()
    claude_chat.ask(fake, "m", CONTEXT, [], "q", can_propose=True, linked=True)
    assert offered(fake) == ["title", "tags"]
    assert "filled in from" in fake.request["system"]             # Claude is told why it can't change them


def test_on_a_card_with_no_claude_folder_claude_is_offered_todays_fields():
    fake = FakeClaude()
    claude_chat.ask(fake, "m", CONTEXT, [], "q", can_propose=True)
    assert offered(fake) == EVERY_FIELD
    assert "filled in from" not in fake.request["system"]
    claude_chat.ask(FakeClaude(), "m", CONTEXT, [], "q", can_propose=True, linked=True)
    assert offered(fake) == EVERY_FIELD and claude_chat.PROPOSE_FIELDS == EVERY_FIELD     # the linked list is its own copy


@pytest.mark.parametrize("field", notes.SYNCED_FIELDS)
def test_a_synced_field_proposed_on_a_linked_card_is_dropped_and_claude_says_why(field):
    value = "pending" if field == "status" else "x"
    answer, proposal = claude_chat.ask(FakeClaude(proposal_with(field, value)), "m", CONTEXT, [], "q",
                                       can_propose=True, linked=True)
    assert proposal is None and field in answer
    with pytest.raises(ValueError, match=field):
        claude_chat.clean_proposal(proposal_with(field, value), linked=True)
    assert claude_chat.clean_proposal(proposal_with(field, value)) is not None         # fine on an unlinked card


def test_the_app_tells_claude_when_the_card_is_linked(tmp_path, projects, work):
    fake = FakeClaude()
    client = create_app(projects, work_jira_folder=str(tmp_path / "work_jira"), claude=lambda: fake).test_client()
    client.post(f"{LINKED}/ask", json={"question": "Update it"})
    assert offered(fake) == ["title", "tags"]
    client.post(f"{URL}/ask", json={"question": "Update it"})
    assert offered(fake) == EVERY_FIELD


def test_approve_on_a_linked_card_refuses_a_synced_field_and_changes_nothing(tmp_path, projects, work):
    client = create_app(projects, work_jira_folder=str(tmp_path / "work_jira"), claude=FakeClaude).test_client()
    before = note_of(projects, "TEST-101")
    body = {"proposal": proposal_with("status", "pending"), "stamp": notes.note_stamp(projects / "TEST-101")}
    response = client.post(f"{LINKED}/apply", json=body)
    assert response.status_code == 400 and "status" in response.json["error"]
    assert note_of(projects, "TEST-101") == before
    ok = client.post(f"{LINKED}/apply", json={**body, "proposal": proposal_with("title", "New name")})
    assert ok.status_code == 200 and fields_of(projects, "TEST-101")["title"] == "New name"


def test_the_global_ask_page_shows_the_status_the_dashboard_shows(projects, client):
    send(client, "blocker", "waiting for Dana")
    blocks, _ = claude_chat.all_projects_context(projects, NOW)
    heading = next(b["text"] for b in blocks if "DEMO-1/note.md" in b["text"]).splitlines()[0]
    assert "status: pending" in heading and "blocked by you: waiting for Dana" in heading
    assert "my_blocker" in claude_chat.ALL_SYSTEM and "my_blocker" in claude_chat.SYSTEM
