"""Tests for what the code reviews of the safety, sync and settings pieces found (2026-11-18),
and for the two choices made after them: a History line that grows is replaced, and a notes folder
that can't be reached does not stop the app from starting.

All folders are fake (tmp_path), all IDs are made up, nothing touches the network.
"""
import logging
import os
from datetime import timedelta

import pytest

import app as app_module
import claude_chat
import notes
import project_note as pn
import work_jira_hooks as hooks
from app import create_app
from test_project_note import history_of, projects, work_project
from test_work_jira_hooks import NOW, REQS, SESSION, begin, setup, tick

NOTE = "---\ntitle: Demo\nstatus: active\n---\nbody text\n\n## History\n- 2026-10-01 · you · first\n"
CP1252_NOTE = "---\ntitle: Café\n---\nbody\n".encode("cp1252")


def make_project(root, folder="DEMO-1", data=NOTE):
    path = root / folder
    path.mkdir(parents=True)
    (path / "note.md").write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def client_for(folder, **kwargs):
    app = create_app(folder, **kwargs)
    app.config.update(TESTING=True)
    return app.test_client()


def log_text(last, now="M3 — email the report", after="nothing after it"):
    return f"# DEMO-42 — Tracking log\n\n## Now working on\n{now}\n\n## Next up\n{after}\n\n## Last update\n{last}\n"


def claude_lines(card):
    return [h["text"] for h in history_of(card) if h["who"] == pn.WHO]


# ---------- safety review 1: a broken link in a project must not blank the list ----------

def test_a_dangling_link_in_a_project_does_not_blank_the_dashboard(tmp_path):
    folder = make_project(tmp_path)
    try:
        (folder / "gone.md").symlink_to(tmp_path / "nowhere.md")
    except OSError:
        pytest.skip("this machine cannot make symlinks")
    assert [p["id"] for p in notes.list_projects(tmp_path)] == ["DEMO-1"]
    assert client_for(tmp_path).get("/api/projects").status_code == 200


# ---------- safety review 2: one bad note must not stop the global Ask Claude page ----------

def test_all_context_skips_a_note_that_is_not_utf8_and_names_it(tmp_path):
    make_project(tmp_path, "DEMO-1")
    make_project(tmp_path, "DEMO-2", CP1252_NOTE)
    blocks, skipped = claude_chat.all_projects_context(tmp_path, NOW)
    all_text = "\n".join(b["text"] for b in blocks)
    assert "body text" in all_text                      # the good note is still sent
    assert len(skipped) == 1 and skipped[0].startswith("DEMO-2/note.md") and "UTF-8" in skipped[0]


# ---------- safety review 3: the last net says the real reason and leaves a trace ----------

def test_a_file_error_caught_by_the_last_net_says_why_and_is_logged(tmp_path, monkeypatch, caplog):
    make_project(tmp_path)

    def disk_full(*args, **kwargs):
        raise OSError(28, "No space left on device", str(tmp_path / "DEMO-1" / "note.md"))
    monkeypatch.setattr(notes, "find_archived", disk_full)
    with caplog.at_level(logging.ERROR):
        response = client_for(tmp_path).post("/api/completed/DEMO-1/restore")
    assert response.status_code == 400
    assert "No space left on device" in response.json["error"] and "note.md" in response.json["error"]
    assert "open in another program" not in response.json["error"]     # that would be a guess, and a wrong one
    assert any(record.exc_info for record in caplog.records)           # the traceback is in the terminal


def test_a_locked_file_caught_by_the_last_net_keeps_the_locked_message(tmp_path, monkeypatch, caplog):
    make_project(tmp_path)

    def locked(*args, **kwargs):
        raise notes.Locked(notes.LOCKED.format("note.md"))
    monkeypatch.setattr(notes, "find_archived", locked)
    with caplog.at_level(logging.ERROR):
        response = client_for(tmp_path).post("/api/completed/DEMO-1/restore")
    assert response.status_code == 400 and response.json["error"] == notes.LOCKED.format("note.md")
    assert caplog.records


def test_a_bad_encoding_caught_by_the_last_net_is_logged(tmp_path, monkeypatch, caplog):
    make_project(tmp_path)

    def not_utf8(*args, **kwargs):
        return b"\xe9".decode("utf-8")
    monkeypatch.setattr(notes, "find_archived", not_utf8)
    with caplog.at_level(logging.ERROR):
        response = client_for(tmp_path).post("/api/completed/DEMO-1/restore")
    assert response.status_code == 400 and "UTF-8" in response.json["error"]
    assert any(record.exc_info for record in caplog.records)


# ---------- safety review 4: create's Goal write really goes through the safe save ----------

def test_create_writes_the_goal_with_the_safe_save(tmp_path, monkeypatch):
    real, calls = os.replace, []

    def second_save_is_locked(src, dst):
        calls.append(dst)
        if len(calls) > 1:
            raise PermissionError(13, "in use")
        return real(src, dst)
    monkeypatch.setattr(notes.os, "replace", second_save_is_locked)
    work = tmp_path / "work_jira" / "DEMO-43"
    work.mkdir(parents=True)
    with pytest.raises(PermissionError):         # save 1 = the new card, save 2 = its Goal
        pn.create(projects(tmp_path), work, "T", "a goal", NOW)
    note = projects(tmp_path) / "DEMO-43" / "note.md"
    assert len(calls) == 2 and "a goal" not in note.read_text(encoding="utf-8")


# ---------- sync review 1: a milestone whose log was fine is not asked about again ----------

def test_a_milestone_already_in_the_log_is_not_asked_about_again_the_next_day(tmp_path):
    settings, projects_folder = setup(tmp_path)
    work = work_project(tmp_path)
    (work / "requirements.md").write_text(REQS, encoding="utf-8")
    pn.create(projects_folder, work, "", "", NOW)
    begin(settings, work)
    tick(work)
    (work / "tracking_log.md").write_text(log_text(f"{NOW:%Y-%m-%d} — M2 ticked, test_parse passes"), encoding="utf-8")
    event = {"cwd": str(work), "stop_hook_active": False, "session_id": SESSION}
    assert hooks.stop(event, settings, NOW) == (0, "")                         # the log is fine: nothing to ask
    assert hooks.stop(event, settings, NOW + timedelta(days=1)) == (0, "")     # past midnight: still nothing


# ---------- sync review 2 (the user's choice): a log entry that grows replaces its History line ----------

def test_an_entry_that_gets_a_detail_line_keeps_one_history_line(tmp_path):
    work = work_project(tmp_path, log=log_text("2026-10-22 — M2 ticked"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    assert claude_lines(card) == ["M2 ticked"]
    (work / "tracking_log.md").write_text(
        log_text("2026-10-22 — M2 ticked\nthe export now also has the date column"), encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    assert claude_lines(card) == ["M2 ticked the export now also has the date column"]
    pn.sync(projects(tmp_path), work, NOW)                                     # and never twice
    assert claude_lines(card) == ["M2 ticked the export now also has the date column"]


def test_two_different_entries_on_one_day_both_stay(tmp_path):
    work = work_project(tmp_path, log=log_text("2026-10-22 — M1 ticked"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    (work / "tracking_log.md").write_text(log_text("2026-10-22 — M1 ticked\n2026-10-22 — M2 ticked"), encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    assert sorted(claude_lines(card)) == ["M1 ticked", "M2 ticked"]


def test_a_longer_word_is_not_a_grown_entry(tmp_path):
    work = work_project(tmp_path, log=log_text("2026-10-22 — M2"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    (work / "tracking_log.md").write_text(log_text("2026-10-22 — M2\n2026-10-22 — M20 ticked"), encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    assert sorted(claude_lines(card)) == ["M2", "M20 ticked"]


def test_a_grown_entry_never_replaces_a_line_you_typed_or_another_day(tmp_path):
    work = work_project(tmp_path, log=log_text("2026-10-22 — M2 ticked\nwith the date column"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    note = card / "note.md"
    text = notes.add_history(note.read_text(encoding="utf-8"), "M2 ticked", "2026-10-22", who="you")
    note.write_text(notes.add_history(text, "M2 ticked", "2026-10-21", who=pn.WHO), encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    lines = [(h["date"], h["who"], h["text"]) for h in history_of(card)]
    assert ("2026-10-22", "you", "M2 ticked") in lines                         # your own line
    assert ("2026-10-21", pn.WHO, "M2 ticked") in lines                        # Claude's line of another day
    assert ("2026-10-22", pn.WHO, "M2 ticked with the date column") in lines


# ---------- sync review 3: how deep "days ago" looks into a work folder ----------

def aged(path, days):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    stamp = NOW.timestamp() - days * 86400
    os.utime(path, (stamp, stamp))
    return stamp


def test_newest_change_stops_at_the_depth_it_is_given(tmp_path):
    old = aged(tmp_path / "top.txt", 9)
    near = aged(tmp_path / "a" / "b" / "near.txt", 5)             # 2 folder levels down: counts
    aged(tmp_path / "a" / "b" / "c" / "deep.txt", 1)              # 3 levels down: not looked at
    assert notes.newest_change(tmp_path, 2) == pytest.approx(near)
    assert notes.newest_change(tmp_path, 0) == pytest.approx(old)
    assert notes.newest_change(tmp_path) > near                   # no limit: the deep file is the newest


def test_a_work_cards_days_ago_looks_two_levels_into_its_work_folder(tmp_path):
    work = tmp_path / "work_jira" / "DEMO-42"
    aged(work / "src" / "pkg" / "near.py", 5)
    aged(work / "src" / "pkg" / "deep" / "deep.py", 1)
    card = {"id": "DEMO-42", "status": "active", "priority": "normal", "source": "work_jira",
            "folder": str(work), "updated": NOW.timestamp() - 9 * 86400}
    assert notes.dashboard([card], NOW)[0]["days_ago"] == 5


# ---------- settings review 1: one bad note must not stop the start or crash the setup check ----------

def settings_file(tmp_path, body):
    path = tmp_path / "settings.ini"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_settings_check_counts_projects_without_opening_their_notes(tmp_path, monkeypatch):
    make_project(tmp_path / "p", "DEMO-1")
    make_project(tmp_path / "p", "DEMO-2", CP1252_NOTE)

    def locked(folder):
        raise PermissionError(13, "in use")
    monkeypatch.setattr(notes, "read_project", locked)             # every note is open in another program
    _, _, findings = app_module.validate_settings(settings_file(tmp_path, f"projects_folder={tmp_path / 'p'}\n"))
    assert [f.text for f in findings if f.level == "bad"] == []
    assert any("(2 projects)" in f.text for f in findings)


# ---------- settings review 2: one rule for "is this a ticket name" ----------

def test_new_project_asks_the_same_ticket_rule_as_import(tmp_path, monkeypatch):
    (tmp_path / "projects").mkdir()
    (tmp_path / "work_jira").mkdir()
    client = client_for(tmp_path / "projects", work_jira_folder=str(tmp_path / "work_jira"))
    assert client.post("/api/projects", json={"id": "abc-123", "work": True}).json["id"] == "ABC-123"
    monkeypatch.setattr(pn, "ticket_key", lambda name: "")         # the one rule now says "not a ticket"...
    assert client.post("/api/projects", json={"id": "abc-124", "work": True}).json["id"] == "abc-124"     # ...so no capitals


# ---------- the user's choice: a notes folder that can't be reached does not stop the start ----------

def test_a_notes_folder_that_is_away_is_bad_for_check_setup_but_does_not_stop_the_app(tmp_path):
    _, _, findings = app_module.validate_settings(settings_file(tmp_path, f"projects_folder={tmp_path / 'nope'}\n"))
    bad = [f for f in findings if f.level == "bad"]
    assert len(bad) == 1 and "does not exist" in bad[0].text and not bad[0].stops_app


def test_the_app_starts_without_its_notes_folder_and_the_page_says_what_to_do(tmp_path, monkeypatch):
    ini = settings_file(tmp_path, f"projects_folder={tmp_path / 'nope'}\nslack_mode=backup\n")
    monkeypatch.setattr(app_module, "load_settings", lambda *a: notes.load_settings(ini))
    monkeypatch.setattr(app_module.slack_live, "start", lambda settings, inbox: None)
    app = app_module.create_app()
    app.config.update(TESTING=True)
    response = app.test_client().get("/api/projects")
    assert response.status_code == 500 and "Can't open the projects folder" in response.json["error"]
    (tmp_path / "nope").mkdir()                                    # the VPN is back: a reload is enough
    assert app.test_client().get("/api/projects").status_code == 200


# ---------- second review: the grown entry picks the right line, only of the same day, and sync problems leave a trace ----------

def write_log(work, last):
    (work / "tracking_log.md").write_text(log_text(last), encoding="utf-8")


def test_a_grown_entry_never_takes_the_line_of_another_entry_of_that_day(tmp_path):
    work = work_project(tmp_path, log=log_text("2026-10-22 — M2 ticked"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    write_log(work, "2026-10-22 — M2 ticked\n2026-10-22 — M2 ticked again after review fix")
    pn.sync(projects(tmp_path), work, NOW)
    assert sorted(claude_lines(card)) == ["M2 ticked", "M2 ticked again after review fix"]
    write_log(work, "2026-10-22 — M2 ticked\n2026-10-22 — M2 ticked again after review fix\nand the tests are green")
    pn.sync(projects(tmp_path), work, NOW)
    assert sorted(claude_lines(card)) == ["M2 ticked", "M2 ticked again after review fix and the tests are green"]


def test_a_grown_entry_replaces_its_longest_earlier_text(tmp_path):
    work = work_project(tmp_path, log=log_text("2026-10-22 — M2 ticked"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    write_log(work, "2026-10-22 — M2 ticked again")                 # two lines of that day now start the same...
    pn.sync(projects(tmp_path), work, NOW)
    note = card / "note.md"
    note.write_text(notes.add_history(note.read_text(encoding="utf-8"), "M2 ticked", "2026-10-22", who=pn.WHO),
                    encoding="utf-8")
    write_log(work, "2026-10-22 — M2 ticked again\nwith detail")    # ...the longer one is the entry that grew
    pn.sync(projects(tmp_path), work, NOW)
    assert sorted(claude_lines(card)) == ["M2 ticked", "M2 ticked again with detail"]


def test_an_entry_without_a_date_only_replaces_todays_line(tmp_path):
    work = work_project(tmp_path, log=log_text("Working on the parser"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    write_log(work, "Working on the parser and the exporter")
    pn.sync(projects(tmp_path), work, NOW)                           # the same day: the line grows
    day1 = NOW.strftime("%Y-%m-%d")
    assert [(h["date"], h["text"]) for h in history_of(card) if h["who"] == pn.WHO] == [
        (day1, "Working on the parser and the exporter")]
    write_log(work, "Working on the parser and the exporter and the email")
    later = NOW + timedelta(days=2)
    pn.sync(projects(tmp_path), work, later)                         # two days later: day 1 keeps its line
    assert [(h["date"], h["text"]) for h in history_of(card) if h["who"] == pn.WHO] == [
        (later.strftime("%Y-%m-%d"), "Working on the parser and the exporter and the email"),
        (day1, "Working on the parser and the exporter")]


def warnings_in(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]


def test_a_card_that_cannot_catch_up_is_logged_once_not_every_30_seconds(tmp_path, caplog):
    work = work_project(tmp_path, log="no headings at all\n")
    notes.new_project(projects(tmp_path), "DEMO-42")
    with caplog.at_level(logging.WARNING):
        assert pn.sync_all(projects(tmp_path), tmp_path / "work_jira", NOW) == []
        assert pn.sync_all(projects(tmp_path), tmp_path / "work_jira", NOW) == []     # the next refresh
    told = warnings_in(caplog)
    assert len(told) == 1 and "DEMO-42" in told[0] and "heading" in told[0]
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        write_log(work, "2026-10-22 — fixed")
        assert pn.sync_all(projects(tmp_path), tmp_path / "work_jira", NOW) == ["DEMO-42"]
        (work / "tracking_log.md").write_text("broken again\n", encoding="utf-8")
        pn.sync_all(projects(tmp_path), tmp_path / "work_jira", NOW)
    assert len(warnings_in(caplog)) == 1                             # it came back: said again, once


def test_a_note_that_is_not_utf8_is_logged_once(tmp_path, caplog):
    make_project(tmp_path, "DEMO-2", CP1252_NOTE)
    with caplog.at_level(logging.WARNING):
        notes.list_projects(tmp_path)
        notes.list_projects(tmp_path)
    told = warnings_in(caplog)
    assert len(told) == 1 and "DEMO-2" in told[0] and "UTF-8" in told[0]


# ---------- third review: an empty-looking log line, and a card that could not be archived ----------

def test_a_line_of_only_bold_marks_under_last_update_is_ignored():
    log = pn.read_tracking_log(log_text("2026-10-22 — M2 ticked\n**\n- **\n****"))
    assert log["last"] == ["2026-10-22 — M2 ticked"]
    assert pn.read_tracking_log(log_text("**"))["last"] == []          # nothing real there: no entry, no crash


def test_a_log_with_a_line_of_only_bold_marks_still_syncs(tmp_path):
    work_project(tmp_path, log=log_text("**\n2026-10-22 — M2 ticked"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    assert pn.sync_all(projects(tmp_path), tmp_path / "work_jira", NOW) == ["DEMO-42"]
    assert claude_lines(card) == ["M2 ticked"]


def test_an_unexpected_error_in_one_card_does_not_stop_the_others_and_is_logged(tmp_path, monkeypatch, caplog):
    work_project(tmp_path, "DEMO-41")
    work_project(tmp_path, "DEMO-42")
    notes.new_project(projects(tmp_path), "DEMO-41")
    notes.new_project(projects(tmp_path), "DEMO-42")
    real = pn.sync

    def sync(projects_folder, work_folder, now):
        if work_folder.name == "DEMO-41":
            raise TypeError("a bug nobody thought of")
        return real(projects_folder, work_folder, now)
    monkeypatch.setattr(pn, "sync", sync)
    with caplog.at_level(logging.WARNING):
        assert pn.sync_all(projects(tmp_path), tmp_path / "work_jira", NOW) == ["DEMO-42"]
    told = warnings_in(caplog)
    assert len(told) == 1 and "DEMO-41" in told[0] and "TypeError" in told[0]


def test_a_card_that_could_not_be_archived_is_logged(tmp_path, caplog):
    cards = tmp_path / "projects"
    make_project(cards, "BAD-1", CP1252_NOTE)
    (tmp_path / "work_jira" / "OTHER-1").mkdir(parents=True)
    with caplog.at_level(logging.WARNING):
        assert pn.archive_gone(cards, tmp_path / "work_jira", NOW) == []
        assert pn.archive_gone(cards, tmp_path / "work_jira", NOW) == []      # the next session: not said twice
    told = warnings_in(caplog)
    assert len(told) == 1 and "BAD-1" in told[0] and "UTF-8" in told[0]
