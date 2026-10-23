"""work_jira sync, slice 1: project_note.py (the helper that creates and syncs dashboard notes).

All folders are fake (tmp_path) and all text is made up.
"""
import os
from datetime import datetime

import pytest

import notes
import project_note as pn

NOW = datetime(2026, 10, 23, 9, 30)

LOG = """# DEMO-42 — Tracking log

<!-- Only two things live here: what we're doing now and what comes next.
     ## Next up = the next milestone. -->

## Now working on
M2 — parse the alarm file
and write its tests.

## Next up
M3 — email the report,
then run it in Spyder.

## Last update
2026-10-22 — M1 ticked, 4 tests green.
"""

PAUSED = LOG.replace("M2 — parse the alarm file\nand write its tests.",
                     "PENDING (user, 2026-10-22): waiting for the lab admin (`admin_questions.md`). "
                     "Draft v2 of requirements. Also open: an idea.")


def work_project(root, name="DEMO-42", log=LOG, files=()):
    """A fake work_jira\\<name> folder with a tracking_log.md (log=None: no log yet)."""
    folder = root / "work_jira" / name
    folder.mkdir(parents=True)
    if log is not None:
        (folder / "tracking_log.md").write_text(log, encoding="utf-8")
    for f in files:
        (folder / f).write_text("x", encoding="utf-8")
    return folder


def projects(root):
    folder = root / "projects"
    folder.mkdir(exist_ok=True)
    return folder


def fields_of(folder):
    return notes.parse_note((folder / "note.md").read_text(encoding="utf-8"))[0]


def history_of(folder):
    return notes.read_history((folder / "note.md").read_text(encoding="utf-8"))


def age(path, seconds):
    """Make a file look older by this many seconds."""
    t = path.stat().st_mtime - seconds
    os.utime(path, (t, t))


# ---------- reading tracking_log.md ----------

def test_read_tracking_log_joins_each_section_into_one_line_and_skips_comments():
    log = pn.read_tracking_log(LOG)
    assert log == {"now": "M2 — parse the alarm file and write its tests.",
                   "next": "M3 — email the report, then run it in Spyder.",
                   "last": "2026-10-22 — M1 ticked, 4 tests green."}


def test_read_tracking_log_headings_are_case_insensitive_and_sections_may_be_empty():
    log = pn.read_tracking_log("## NOW WORKING ON\n\n## next up\n\n## Last Update\n")
    assert log == {"now": "", "next": "", "last": ""}


def test_read_tracking_log_missing_headings_is_a_plain_error():
    with pytest.raises(pn.SyncError, match="## Next up.*## Last update"):
        pn.read_tracking_log("## Now working on\nsomething\n")


def test_status_from_now_working_on():
    assert pn.status_from("M2 — parse the file") == ("active", "")
    assert pn.status_from("PENDING (user, 2026-10-22): waiting for the lab admin (`q.md`). More text.") == (
        "pending", "waiting for the lab admin (`q.md`).")
    assert pn.status_from("pending: vendor reply") == ("pending", "vendor reply")
    assert pn.status_from("PENDING") == ("pending", "")


def test_last_update_splits_date_and_text_with_any_dash():
    assert pn.last_update("2026-10-21 — grill-me done: D1-D9 decided.", NOW) == (
        "2026-10-21", "grill-me done: D1-D9 decided.")
    assert pn.last_update("2026-10-21 - short dash", NOW) == ("2026-10-21", "short dash")
    assert pn.last_update("no date here", NOW) == ("2026-10-23", "no date here")
    assert pn.last_update("", NOW) is None


# ---------- which work_jira folder is a project ----------

def test_work_project_is_the_folder_right_under_work_jira(tmp_path):
    folder = work_project(tmp_path)
    (folder / "tests").mkdir()
    wj = tmp_path / "work_jira"
    assert pn.work_project(wj, folder) == folder
    assert pn.work_project(wj, folder / "tests") == folder      # Claude may cd deeper
    assert pn.work_project(wj, wj) is None
    assert pn.work_project(wj, tmp_path) is None
    (wj / "_templates").mkdir()
    assert pn.work_project(wj, wj / "_templates") is None
    assert pn.work_project("", folder) is None                  # work_jira_folder= not set


# ---------- sync ----------

def test_sync_copies_next_status_and_a_claude_history_line(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42", "Alarm update")
    pn.sync(projects(tmp_path), work, NOW)
    f = fields_of(card)
    assert f["next"] == "M3 — email the report, then run it in Spyder."
    assert (f["status"], f["blocked_by"], f["priority"]) == ("active", "", "normal")
    assert (f["source"], f["folder"]) == ("work_jira", str(work))
    assert history_of(card) == [{"date": "2026-10-22", "who": "Claude", "text": "M1 ticked, 4 tests green."}]


def test_sync_sets_pending_and_blocked_by_then_clears_them(tmp_path):
    work = work_project(tmp_path, log=PAUSED)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    assert (fields_of(card)["status"], fields_of(card)["blocked_by"]) == (
        "pending", "waiting for the lab admin (`admin_questions.md`).")
    (work / "tracking_log.md").write_text(LOG, encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    assert (fields_of(card)["status"], fields_of(card)["blocked_by"]) == ("active", "")


def test_sync_never_repeats_a_history_line_and_never_touches_priority(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    note = card / "note.md"
    note.write_text(notes.set_fields(note.read_text(encoding="utf-8"), {"priority": "critical"}), encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    pn.sync(projects(tmp_path), work, NOW)
    assert len(history_of(card)) == 1
    assert fields_of(card)["priority"] == "critical"


def test_sync_adds_a_new_history_line_on_top_when_last_update_changes(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    (work / "tracking_log.md").write_text(LOG.replace("2026-10-22 — M1 ticked, 4 tests green.",
                                                      "2026-10-23 — M2 ticked."), encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    assert [h["text"] for h in history_of(card)] == ["M2 ticked.", "M1 ticked, 4 tests green."]


def test_sync_keeps_body_and_unknown_fields(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    note = card / "note.md"
    note.write_text(note.read_text(encoding="utf-8").replace("## Goal\n", "## Goal\nKeep me.\n")
                    .replace("tags:\n", "tags: rf\nowner: me\n"), encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    text = note.read_text(encoding="utf-8")
    assert "Keep me." in text and fields_of(card)["owner"] == "me" and fields_of(card)["tags"] == "rf"


def test_sync_without_a_card_or_with_a_bad_log_changes_nothing(tmp_path):
    work = work_project(tmp_path)
    with pytest.raises(pn.NoCard):
        pn.sync(projects(tmp_path), work, NOW)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    before = (card / "note.md").read_text(encoding="utf-8")
    (work / "tracking_log.md").write_text("just text\n", encoding="utf-8")
    with pytest.raises(pn.SyncError):
        pn.sync(projects(tmp_path), work, NOW)
    assert (card / "note.md").read_text(encoding="utf-8") == before


def test_needs_sync_when_the_log_is_newer_than_the_card(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    age(work / "tracking_log.md", 60)
    assert not pn.needs_sync(card, work)
    age(card / "note.md", 120)
    assert pn.needs_sync(card, work)
    pn.sync(projects(tmp_path), work, NOW)
    assert not pn.needs_sync(card, work)


# ---------- create ----------

def test_create_makes_a_filled_card_with_goal(tmp_path):
    work = work_project(tmp_path)
    card, what = pn.create(projects(tmp_path), work, "Alarm update", "Parse alarms.\nEmail a daily report.", NOW)
    assert what == "created" and card == projects(tmp_path) / "DEMO-42"
    f = fields_of(card)
    assert (f["title"], f["jira"], f["source"], f["priority"]) == ("Alarm update", "DEMO-42", "work_jira", "normal")
    assert f["next"].startswith("M3")
    body = notes.parse_note((card / "note.md").read_text(encoding="utf-8"))[1]
    assert "## Goal\nParse alarms.\nEmail a daily report.\n" in body
    assert len(history_of(card)) == 1


def test_create_works_for_a_non_ticket_project_and_before_the_log_exists(tmp_path):
    work = work_project(tmp_path, name="beaver_reports", log=None)
    card, what = pn.create(projects(tmp_path), work, "", "", NOW)
    f = fields_of(card)
    assert what == "created"
    assert (f["title"], f["jira"], f["source"], f["folder"]) == ("beaver_reports", "", "work_jira", str(work))


def test_create_when_the_card_exists_only_syncs(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42", "Mine")
    again, what = pn.create(projects(tmp_path), work, "Other title", "goal", NOW)
    assert (again, what) == (card, "exists")
    assert fields_of(card)["title"] == "Mine" and fields_of(card)["source"] == "work_jira"


def test_create_restores_the_newest_archived_card_instead_of_making_a_second(tmp_path):
    work = work_project(tmp_path)
    old = notes.new_project(projects(tmp_path), "DEMO-42", "Old")
    notes.archive_project(projects(tmp_path), old, NOW)
    newer = notes.new_project(projects(tmp_path), "DEMO-42", "Newer")
    notes.archive_project(projects(tmp_path), newer, datetime(2026, 10, 24))   # gets a time suffix
    card, what = pn.create(projects(tmp_path), work, "", "", NOW)
    assert what == "restored" and card == projects(tmp_path) / "DEMO-42"
    assert fields_of(card)["title"] == "Newer" and fields_of(card)["status"] == "active"
    assert len(list((projects(tmp_path) / "_archive").iterdir())) == 1


# ---------- archive check: folders that left work_jira ----------

def test_archive_gone_archives_only_work_jira_cards_whose_folder_left(tmp_path):
    wj = tmp_path / "work_jira"
    stay = work_project(tmp_path, "DEMO-1")
    gone = work_project(tmp_path, "DEMO-2")
    pn.create(projects(tmp_path), stay, "", "", NOW)
    pn.create(projects(tmp_path), gone, "", "", NOW)
    notes.new_project(projects(tmp_path), "my_idea")         # personal: no source: work_jira
    os.rename(gone, tmp_path / "prod_DEMO-2")                 # moved to prod
    assert pn.archive_gone(projects(tmp_path), wj, NOW) == ["DEMO-2"]
    assert {p["id"] for p in notes.list_projects(projects(tmp_path))} == {"DEMO-1", "my_idea"}
    archived = notes.find_archived(projects(tmp_path), "DEMO-2")
    assert history_of(archived)[0]["text"] == pn.MOVED_TO_PROD
    assert fields_of(archived)["status"] == "done"


@pytest.mark.parametrize("problem", ["missing", "empty", "not set"])
def test_archive_gone_does_nothing_when_work_jira_is_missing_or_empty(tmp_path, problem):
    work = work_project(tmp_path, "DEMO-1")
    pn.create(projects(tmp_path), work, "", "", NOW)
    os.rename(work, tmp_path / "elsewhere")
    wj = tmp_path / "work_jira"
    if problem == "missing":
        os.rename(wj, tmp_path / "renamed")
    elif problem == "empty":
        (wj / "_templates").mkdir()                            # no project folders, only templates
    else:
        wj = ""
    assert pn.archive_gone(projects(tmp_path), wj, NOW) == []
    assert notes.find_project(projects(tmp_path), "DEMO-1")


def test_archive_gone_compares_names_ignoring_case(tmp_path):
    work = work_project(tmp_path, "demo-1")
    pn.create(projects(tmp_path), work, "", "", NOW)
    os.rename(work, work.parent / "tmp")
    os.rename(work.parent / "tmp", work.parent / "DEMO-1")    # same folder on Windows
    assert pn.archive_gone(projects(tmp_path), tmp_path / "work_jira", NOW) == []


# ---------- command line (what Claude runs) ----------

def settings_ini(tmp_path, work_jira=True):
    ini = tmp_path / "settings.ini"
    ini.write_text(f"projects_folder={projects(tmp_path)}\n"
                   f"work_jira_folder={tmp_path / 'work_jira' if work_jira else ''}\n", encoding="utf-8")
    return ini


def test_command_create_then_sync(tmp_path, capsys):
    work_project(tmp_path)
    ini = settings_ini(tmp_path)
    assert pn.main(["create", "DEMO-42", "--title", "Alarm update", "--goal", "Parse alarms."], ini, NOW) == 0
    assert "DEMO-42" in capsys.readouterr().out
    assert fields_of(projects(tmp_path) / "DEMO-42")["title"] == "Alarm update"
    assert pn.main(["sync", "DEMO-42"], ini, NOW) == 0


@pytest.mark.parametrize("args, says", [
    (["create", "NOPE-1"], "No folder NOPE-1 in"),
    (["sync", "DEMO-42"], "no dashboard card"),
    (["create", "../x"], "No folder"),
])
def test_command_errors_are_plain_english(tmp_path, capsys, args, says):
    work_project(tmp_path)
    assert pn.main(args, settings_ini(tmp_path), NOW) == 1
    assert says in capsys.readouterr().err


def test_command_without_work_jira_folder_setting_says_what_to_add(tmp_path, capsys):
    assert pn.main(["sync", "DEMO-42"], settings_ini(tmp_path, work_jira=False), NOW) == 1
    assert "work_jira_folder=" in capsys.readouterr().err
