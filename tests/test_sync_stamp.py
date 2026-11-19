"""The S2 sync: the stored stamp, more sync moments, and a more careful reading of tracking_log.md.

All folders are fake (tmp_path), all text is made up, nothing touches the network.
"""
import os
from datetime import datetime, timedelta

import pytest

import notes
import project_note as pn
import work_jira_hooks as hooks
from app import create_app
from test_project_note import LOG, REQUIREMENTS, fields_of, history_of, projects, work_project
from test_work_jira_hooks import REQS, SESSION, begin, setup, stop, tick

NOW = datetime(2026, 10, 23, 9, 30)


def synced_card(tmp_path, name="DEMO-42", **kwargs):
    """(work folder, card) with the card synced once."""
    work = work_project(tmp_path, name, **kwargs)
    card = notes.new_project(projects(tmp_path), name)
    pn.sync(projects(tmp_path), work, NOW)
    return work, card


def same_mtime_as(path, other):
    stat = other.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))


# ---------- 1. the stored stamp ----------

def test_a_card_that_was_never_synced_needs_a_sync(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    assert pn.needs_sync(card, work)
    pn.sync(projects(tmp_path), work, NOW)
    assert not pn.needs_sync(card, work)


def test_an_edit_in_the_same_second_is_seen_through_the_size(tmp_path):
    work, card = synced_card(tmp_path)
    log = work / "tracking_log.md"
    before = log.stat()
    log.write_text(log.read_text(encoding="utf-8").replace("M3 — email", "M3 — send the long email"), encoding="utf-8")
    os.utime(log, ns=(before.st_atime_ns, before.st_mtime_ns))      # same time as before, other size
    assert pn.needs_sync(card, work)


def test_a_copied_older_file_is_seen_through_its_time(tmp_path):
    work, card = synced_card(tmp_path)
    log = work / "tracking_log.md"
    text = log.read_text(encoding="utf-8")
    log.write_text(text.replace("M3", "M4"), encoding="utf-8")     # same size, other text
    stamp = log.stat().st_mtime_ns - 5_000_000_000
    os.utime(log, ns=(stamp, stamp))                                 # copied from a file that is older than the card
    assert pn.needs_sync(card, work)


def test_a_card_touched_later_does_not_hide_a_change_in_the_log(tmp_path):
    work, card = synced_card(tmp_path)
    log = work / "tracking_log.md"
    log.write_text(log.read_text(encoding="utf-8").replace("M3 — email", "M3 — fax"), encoding="utf-8")
    future = card.joinpath("note.md").stat().st_mtime_ns + 60_000_000_000
    os.utime(card / "note.md", ns=(future, future))                  # card saved by hand after the log changed
    assert pn.needs_sync(card, work)


def test_a_card_touched_later_without_a_log_change_needs_nothing(tmp_path):
    work, card = synced_card(tmp_path)
    old = card.joinpath("note.md").stat().st_mtime_ns - 60_000_000_000
    os.utime(card / "note.md", ns=(old, old))
    assert not pn.needs_sync(card, work)


def test_a_ticked_milestone_in_requirements_needs_a_sync(tmp_path):
    work, card = synced_card(tmp_path)
    (work / "requirements.md").write_text(REQUIREMENTS, encoding="utf-8")
    assert pn.needs_sync(card, work)
    pn.sync(projects(tmp_path), work, NOW)
    assert not pn.needs_sync(card, work)
    reqs = work / "requirements.md"
    reqs.write_text(reqs.read_text(encoding="utf-8").replace("- [ ] M3a", "- [x] M3a"), encoding="utf-8")
    assert pn.needs_sync(card, work)


def test_no_log_means_nothing_to_sync(tmp_path):
    work = work_project(tmp_path, log=None)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    assert not pn.needs_sync(card, work)


def test_the_stamp_is_a_field_in_the_card(tmp_path):
    work, card = synced_card(tmp_path)
    log = work / "tracking_log.md"
    info = log.stat()
    assert fields_of(card)[pn.STAMP_FIELD].startswith(f"{info.st_mtime_ns}-{info.st_size} ")


def test_sync_writes_nothing_when_the_card_would_not_change(tmp_path):
    work, card = synced_card(tmp_path)
    note = card / "note.md"
    old = note.stat().st_mtime_ns - 60_000_000_000
    os.utime(note, ns=(old, old))
    pn.sync(projects(tmp_path), work, NOW)
    assert note.stat().st_mtime_ns == old


def test_a_touched_log_with_the_same_text_updates_only_the_stamp(tmp_path):
    work, card = synced_card(tmp_path)
    log = work / "tracking_log.md"
    new_time = log.stat().st_mtime_ns + 7_000_000_000
    os.utime(log, ns=(new_time, new_time))
    assert pn.needs_sync(card, work)
    before = history_of(card)
    pn.sync(projects(tmp_path), work, NOW)
    assert not pn.needs_sync(card, work) and history_of(card) == before


def test_mark_older_than_log_is_gone():
    assert not hasattr(pn, "mark_older_than_log")


def test_a_log_with_bad_headings_stays_in_need_of_a_sync(tmp_path):
    work = work_project(tmp_path, log="## Now working on\nx\n")
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    with pytest.raises(pn.SyncError):
        pn.sync(projects(tmp_path), work, NOW)
    assert pn.needs_sync(card, work)


# ---------- 2. more moments to sync ----------

def stale_card(tmp_path, name="DEMO-42"):
    """A synced card whose work folder moved on to M4 afterwards (like a hand edit, or a session that was killed)."""
    work, card = synced_card(tmp_path, name)
    log = work / "tracking_log.md"
    log.write_text(log.read_text(encoding="utf-8").replace("M2 — parse the alarm file", "M7 — newer work"),
                   encoding="utf-8")
    return work, card


def test_session_start_syncs_a_card_that_is_behind(tmp_path):
    settings, projects_folder = setup(tmp_path)
    work, card = stale_card(tmp_path)
    assert fields_of(card)["working_on"].startswith("M2")
    hooks.session_start({"cwd": str(tmp_path), "source": "startup"}, settings, NOW)
    assert fields_of(card)["working_on"].startswith("M7")


def test_session_start_goes_on_when_one_folder_has_a_bad_log(tmp_path):
    settings, _ = setup(tmp_path)
    work_project(tmp_path, "DEMO-1", log="no headings\n")
    work, card = stale_card(tmp_path, "DEMO-2")
    notes.new_project(projects(tmp_path), "DEMO-1")
    hooks.session_start({"cwd": str(tmp_path), "source": "startup"}, settings, NOW)
    assert fields_of(card)["working_on"].startswith("M7")


@pytest.fixture
def work_client(tmp_path):
    (tmp_path / "work_jira").mkdir(exist_ok=True)
    app = create_app(projects(tmp_path), work_jira_folder=str(tmp_path / "work_jira"))
    app.config.update(TESTING=True)
    return app.test_client()


def test_the_dashboard_list_syncs_a_card_that_is_behind(tmp_path, work_client):
    stale_card(tmp_path)
    rows = work_client.get("/api/projects").json["projects"]
    assert rows[0]["working_on"].startswith("M7")


def test_the_dashboard_list_still_answers_when_one_card_cannot_sync(tmp_path, work_client):
    work_project(tmp_path, "DEMO-1", log="no headings\n")
    notes.new_project(projects(tmp_path), "DEMO-1")
    (tmp_path / "work_jira" / "DEMO-3").mkdir()
    (tmp_path / "work_jira" / "DEMO-3" / "tracking_log.md").write_bytes(b"## Now working on\n\xe9\n")
    notes.new_project(projects(tmp_path), "DEMO-3")
    stale_card(tmp_path, "DEMO-2")
    response = work_client.get("/api/projects")
    assert response.status_code == 200
    assert {r["id"]: r["working_on"][:2] for r in response.json["projects"]}["DEMO-2"] == "M7"


def test_the_dashboard_list_answers_without_a_work_jira_folder(tmp_path):
    notes.new_project(projects(tmp_path), "DEMO-1")
    for folder in ("", str(tmp_path / "nowhere")):
        app = create_app(projects(tmp_path), work_jira_folder=folder)
        app.config.update(TESTING=True)
        assert app.test_client().get("/api/projects").status_code == 200


def test_the_dashboard_list_reads_no_work_files_when_nothing_changed(tmp_path, work_client, monkeypatch):
    work, _ = synced_card(tmp_path)
    reads = []
    original = pn.read_tracking_log
    monkeypatch.setattr(pn, "read_tracking_log", lambda text: reads.append(1) or original(text))
    assert work_client.get("/api/projects").status_code == 200
    assert reads == []


# ---------- 3. PENDING ----------

@pytest.mark.parametrize("text", [
    "- PENDING (user, 2026-10-22): waiting for the lab admin. More.",
    "* **PENDING** (user, 2026-10-22): waiting for the lab admin. More.",
    "**PENDING:** waiting for the lab admin. More.",
    "pending: waiting for the lab admin. More.",
])
def test_pending_with_bullets_and_bold_marks(text):
    assert pn.pending_parts(text) == ("waiting for the lab admin.", "More.")


@pytest.mark.parametrize("text", [
    "Pending review of M3",
    "PENDING the lab admin",
    "M2 — PENDING items list",
    "pendingness: none",
])
def test_pending_needs_a_bracket_or_a_colon(text):
    assert pn.pending_parts(text) is None
    assert pn.status_from(text) == ("active", "")


def test_pending_reason_is_not_cut_at_an_abbreviation():
    text = "PENDING (user, 2026-10-22): waiting for Dr. Smith to reply. Draft v2 meanwhile."
    assert pn.pending_parts(text) == ("waiting for Dr. Smith to reply.", "Draft v2 meanwhile.")
    assert pn.pending_parts("PENDING: reply from J. Smith, e.g. by mail. Next.") == (
        "reply from J. Smith, e.g. by mail.", "Next.")
    assert pn.pending_parts("PENDING: waiting for the vendor. then more") == ("waiting for the vendor. then more", "")


def test_a_bulleted_working_on_loses_its_bullet():
    assert pn.working_on_from("- M2 — parse the file") == "M2 — parse the file"


# ---------- 4. last update ----------

def last_lines(*lines):
    return pn.read_tracking_log(LOG.replace("2026-10-22 — M1 ticked, 4 tests green.\n", "\n".join(lines) + "\n"))["last"]


def test_undated_lines_after_a_dated_line_belong_to_that_entry():
    assert last_lines("2026-10-22 — M1 ticked,", "4 tests green.", "2026-10-21 — older.", "more older") == [
        "2026-10-22 — M1 ticked, 4 tests green."]
    assert last_lines("2026-10-21 — older.", "second line of older.", "2026-10-22 — newer.", "- and its detail") == [
        "2026-10-22 — newer. - and its detail"]


def test_lines_before_the_first_dated_line_are_not_an_entry():
    assert last_lines("stray note", "2026-10-21 — dated.") == ["2026-10-21 — dated."]


def test_bold_dates_and_the_date_colon_form():
    assert pn.last_update("**2026-10-21** — M1 ticked", NOW) == ("2026-10-21", "M1 ticked")
    assert pn.last_update("**2026-10-21 — M1 ticked**", NOW) == ("2026-10-21", "M1 ticked")
    assert pn.last_update("- **2026-10-21:** M1 ticked", NOW) == ("2026-10-21", "M1 ticked")
    assert pn.last_update("Date: 2026-10-21 — M1 ticked", NOW) == ("2026-10-21", "M1 ticked")
    assert pn.last_update("**Date:** 2026-10-21", NOW) == ("2026-10-21", "")
    assert last_lines("**2026-10-20** — older", "date: 2026-10-22 — newer") == ["date: 2026-10-22 — newer"]


def test_a_date_line_with_the_text_on_the_next_lines_syncs_with_that_text(tmp_path):
    log = LOG.replace("2026-10-22 — M1 ticked, 4 tests green.", "**Date:** 2026-10-22\nM1 ticked.\n4 tests green.")
    work = work_project(tmp_path, log=log)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    assert history_of(card)[0] == {"date": "2026-10-22", "who": "Claude", "text": "M1 ticked. 4 tests green."}


# ---------- 5. a log that is not UTF-8 ----------

def ansi_log(work):
    (work / "tracking_log.md").write_bytes(LOG.replace("M2 —", "M2 café").encode("cp1252"))


def test_a_log_that_is_not_utf8_is_a_plain_sync_error(tmp_path):
    work = work_project(tmp_path)
    notes.new_project(projects(tmp_path), "DEMO-42")
    ansi_log(work)
    with pytest.raises(pn.SyncError, match="UTF-8"):
        pn.sync(projects(tmp_path), work, NOW)


def test_the_stop_hook_says_what_to_do_about_a_log_that_is_not_utf8(tmp_path):
    settings, _ = setup(tmp_path)
    work, card = synced_card(tmp_path)
    ansi_log(work)
    code, message = stop(settings, work)
    assert code == 2 and "UTF-8" in message


def test_session_start_survives_a_log_that_is_not_utf8(tmp_path):
    settings, _ = setup(tmp_path)
    work, card = synced_card(tmp_path)
    ansi_log(work)
    context, _ = hooks.session_start({"cwd": str(work), "source": "startup", "session_id": SESSION}, settings, NOW)
    assert context == ""                          # a broken log pauses the ticket: the Stop hook asks to fix it


def test_the_milestone_check_survives_a_log_that_is_not_utf8(tmp_path):
    settings, work = ticket_with_card(tmp_path)
    begin(settings, work)
    tick(work)
    ansi_log(work)
    assert hooks.milestone_check(work, {"session_id": SESSION}, NOW) == ""


# ---------- 6. days ago ----------

def make_card(tmp_path, name, stamp, extra=()):
    folder = tmp_path / "cards" / name
    folder.mkdir(parents=True)
    (folder / "note.md").write_text("---\ntitle: x\n" + "".join(f"{k}: {v}\n" for k, v in extra) + "---\nbody\n",
                                    encoding="utf-8")
    os.utime(folder / "note.md", (stamp, stamp))
    return folder


def test_newest_change_skips_dot_files_and_system_files(tmp_path):
    folder = make_card(tmp_path, "DEMO-1", 1000)
    for name in (".DS_Store", "desktop.ini", "Thumbs.db", "THUMBS.DB"):
        (folder / name).write_text("x")
        os.utime(folder / name, (9000, 9000))
    (folder / ".hidden").mkdir()
    (folder / ".hidden" / "a.md").write_text("x")
    os.utime(folder / ".hidden" / "a.md", (9000, 9000))
    assert notes.newest_change(folder) == 1000


def test_newest_change_survives_a_dangling_symlink(tmp_path):
    folder = make_card(tmp_path, "DEMO-1", 1000)
    try:
        (folder / "gone.md").symlink_to(tmp_path / "nowhere.md")
    except OSError:
        pytest.skip("this machine cannot make symlinks")
    assert notes.newest_change(folder) == 1000


def test_dashboard_never_shows_a_negative_number_of_days():
    future = (NOW + timedelta(days=2)).timestamp()
    rows = notes.dashboard([{"id": "A", "status": "active", "priority": "normal", "updated": future}], NOW)
    assert rows[0]["days_ago"] == 0 and not rows[0]["quiet"]


def test_a_work_card_counts_the_work_folders_files_too(tmp_path):
    work = work_project(tmp_path, "DEMO-1")
    old = (NOW - timedelta(days=20)).timestamp()
    recent = (NOW - timedelta(days=1)).timestamp()
    card = make_card(tmp_path, "DEMO-1", old, extra=[("source", "work_jira"), ("folder", work)])
    os.utime(work / "tracking_log.md", (recent, recent))
    project = notes.read_project(card)
    assert notes.dashboard([project], NOW)[0]["days_ago"] == 1


def test_a_card_that_is_not_a_work_card_ignores_its_folder_field(tmp_path):
    other = tmp_path / "somewhere"
    other.mkdir()
    (other / "a.md").write_text("x")
    old = (NOW - timedelta(days=20)).timestamp()
    os.utime(other / "a.md", (NOW.timestamp(), NOW.timestamp()))
    card = make_card(tmp_path, "DEMO-1", old, extra=[("folder", other)])
    assert notes.dashboard([notes.read_project(card)], NOW)[0]["days_ago"] == 20


def test_a_missing_work_folder_is_ignored(tmp_path):
    old = (NOW - timedelta(days=20)).timestamp()
    card = make_card(tmp_path, "DEMO-1", old, extra=[("source", "work_jira"), ("folder", tmp_path / "nope")])
    assert notes.dashboard([notes.read_project(card)], NOW)[0]["days_ago"] == 20


def test_the_work_folders_hidden_files_do_not_count(tmp_path):
    work = work_project(tmp_path, "DEMO-1")
    (work / ".claude").mkdir()
    (work / ".claude" / "milestone-x.json").write_text("{}")
    old = (NOW - timedelta(days=20)).timestamp()
    for f in (work / "tracking_log.md", work / ".claude" / "milestone-x.json"):
        os.utime(f, (old if f.name == "tracking_log.md" else NOW.timestamp(),) * 2)
    card = make_card(tmp_path, "DEMO-1", old, extra=[("source", "work_jira"), ("folder", work)])
    assert notes.dashboard([notes.read_project(card)], NOW)[0]["days_ago"] == 20


# ---------- 7. the loop and the reminder ----------

def test_one_bad_folder_does_not_stop_the_sync_loop(tmp_path, monkeypatch):
    settings, _ = setup(tmp_path)
    work_project(tmp_path, "DEMO-1")
    _, card = stale_card(tmp_path, "DEMO-2")
    notes.new_project(projects(tmp_path), "DEMO-1")
    real = pn.needs_sync

    def flaky(card_folder, work_folder):
        if work_folder.name == "DEMO-1":
            raise OSError("a drive that went away")
        return real(card_folder, work_folder)

    monkeypatch.setattr(pn, "needs_sync", flaky)
    hooks.sync_all(str(projects(tmp_path)), str(tmp_path / "work_jira"), NOW)
    assert fields_of(card)["working_on"].startswith("M7")


def ticket_with_card(tmp_path):
    settings, projects_folder = setup(tmp_path)
    work = work_project(tmp_path)
    (work / "requirements.md").write_text(REQS, encoding="utf-8")
    pn.create(projects_folder, work, "", "", NOW)
    return settings, work


def test_a_dropped_log_reminder_is_asked_again_at_the_next_reply(tmp_path):
    settings, work = ticket_with_card(tmp_path)
    begin(settings, work)
    tick(work)
    assert stop(settings, work, active=True) == (0, "")        # Claude Code was already holding the reply: dropped
    code, message = stop(settings, work)
    assert code == 2 and "M2 ticked" in message
    assert stop(settings, work) == (0, "")                     # given once, not again
