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
                   "last": ["2026-10-22 — M1 ticked, 4 tests green."]}


def test_read_tracking_log_headings_are_case_insensitive_and_sections_may_be_empty():
    log = pn.read_tracking_log("## NOW WORKING ON\n\n## next up\n\n## Last Update\n")
    assert log == {"now": "", "next": "", "last": []}


def test_read_tracking_log_missing_headings_is_a_plain_error():
    with pytest.raises(pn.SyncError, match="## Next up.*## Last update"):
        pn.read_tracking_log("## Now working on\nsomething\n")


def test_status_from_now_working_on():
    assert pn.status_from("M2 — parse the file") == ("active", "")
    assert pn.status_from("PENDING (user, 2026-10-22): waiting for the lab admin (`q.md`). More text.") == (
        "pending", "waiting for the lab admin (`q.md`).")
    assert pn.status_from("pending: vendor reply") == ("pending", "vendor reply")
    assert pn.status_from("PENDING") == ("pending", "")


def test_working_on_from_now_working_on():
    assert pn.working_on_from("M2 — parse the file") == "M2 — parse the file"
    assert pn.working_on_from("**M4 — demo login** · Done when: demo check prints") == (
        "M4 — demo login · Done when: demo check prints")              # Markdown bold marks dropped
    # pending: the reason is already in blocked_by, so only the text after it
    assert pn.working_on_from("PENDING (user, 2026-10-22): waiting for the lab admin. Draft v2. Idea.") == (
        "Draft v2. Idea.")
    assert pn.working_on_from("PENDING (user, 2026-10-22): waiting for the lab admin.") == ""
    assert pn.working_on_from("PENDING") == ""


def test_last_update_splits_date_and_text_with_any_dash():
    assert pn.last_update("2026-10-21 — grill-me done: D1-D9 decided.", NOW) == (
        "2026-10-21", "grill-me done: D1-D9 decided.")
    assert pn.last_update("2026-10-21 - short dash", NOW) == ("2026-10-21", "short dash")
    assert pn.last_update("no date here", NOW) == (None, "no date here")      # sync then uses today
    assert pn.last_update("- 2026-10-21 — as a bullet", NOW) == ("2026-10-21", "as a bullet")
    assert pn.last_update("", NOW) is None


def test_read_tracking_log_only_level_1_and_2_headings_end_a_section():
    log = pn.read_tracking_log(LOG.replace("then run it in Spyder.", "### Phase 2\n#42 needs review."))
    assert log["next"] == "M3 — email the report, ### Phase 2 #42 needs review."


def last_lines(*lines):
    """LOG with these lines under ## Last update (instead of the one it has)."""
    return pn.read_tracking_log(LOG.replace("2026-10-22 — M1 ticked, 4 tests green.\n", "\n".join(lines) + "\n"))["last"]


def test_read_tracking_log_last_update_is_the_newest_dated_line_wherever_it_is():
    assert last_lines("2026-10-22 — newer.", "2026-10-21 — older.") == ["2026-10-22 — newer."]   # newest on top
    assert last_lines("2026-10-21 — older.", "2026-10-22 — newer.") == ["2026-10-22 — newer."]   # appended at bottom
    assert last_lines("- 2026-10-21 — older.", "- 2026-10-22 — bullet.") == ["- 2026-10-22 — bullet."]
    assert last_lines("no date here", "2026-10-21 — dated.") == ["2026-10-21 — dated."]       # a dated line wins


def test_read_tracking_log_last_update_without_dates_is_the_first_line():
    assert last_lines("first undated.", "second undated.") == ["first undated."]


def test_read_tracking_log_last_update_keeps_every_line_of_the_newest_day():
    assert last_lines("2026-10-22 — one.", "2026-10-21 — older.", "2026-10-22 — two.") == [
        "2026-10-22 — one.", "2026-10-22 — two."]


# ---------- reading milestones from requirements.md ----------

REQUIREMENTS = """# DEMO-42 — Requirements

<!-- - [ ] M9 — a commented-out line is not a milestone -->
## Milestones
- [ ] M<n> — <what it delivers> · Done when: <proof>
- [x] M1 — read the alarm file · Done when: test_read_alarms passes
- [X] M2 — parse it · Done when: user check — numbers match Spyder
- [ ] M3a — email the report · Done when: test_email passes
* [ ] M3b — schedule it · Done when: user check — it runs at 6:00
- [x] Mx — not a milestone ID
  - [ ] m4 — written in lower case · Done when: user check — ok
"""


def test_read_milestones_in_file_order_with_ticked_or_not():
    assert pn.read_milestones(REQUIREMENTS) == {"M1": True, "M2": True, "M3a": False, "M3b": False, "M4": False}


def test_template_lines_with_placeholders_are_not_milestones():
    assert pn.read_milestones("- [ ] M1 — <what it delivers> · Done when: <proof>\n") == {}
    assert pn.read_milestones("none yet — waiting for approval\n") == {}


def test_milestone_lines_written_a_little_differently_still_count():
    text = ("- [x] **M1** — bold ID\n- [x] M3A — capital letter\n"
            "- [x] M4 — latency < 5 ms and > 2 ms · Done when: test_latency passes\n")
    assert pn.read_milestones(text) == {"M1": True, "M3a": True, "M4": True}


def test_milestone_names_are_the_short_names_in_file_order():
    assert pn.milestone_names(REQUIREMENTS) == {
        "M1": "read the alarm file", "M2": "parse it", "M3a": "email the report",
        "M3b": "schedule it", "M4": "written in lower case"}
    # bold ID and `code` marks dropped, cut before "· Done when", no dash after the ID
    assert pn.milestone_names("- [ ] **M7** — job logic in `job.py` · Done when: 10 tests pass\n") == {
        "M7": "job logic in job.py"}
    assert pn.milestone_names("- [ ] M8: a colon\n- [ ] M9\n") == {"M8": "a colon", "M9": ""}


def test_milestones_in_a_folder_without_requirements_md_is_empty(tmp_path):
    assert pn.folder_milestones(tmp_path) == {}
    (tmp_path / "requirements.md").write_text("﻿" + REQUIREMENTS, encoding="utf-8")   # Notepad adds a BOM
    assert pn.folder_milestones(tmp_path)["M1"] is True
    (tmp_path / "requirements.md").write_bytes("- [x] M1 — caf\u00e9 \u2013 a\n".encode("cp1252"))  # saved as ANSI
    assert pn.folder_milestones(tmp_path) == {"M1": True}


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


def test_sync_copies_working_on_and_drops_bold_marks(tmp_path):
    work = work_project(tmp_path, log=LOG.replace("M3 — email", "**M3 — email**"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    f = fields_of(card)
    assert f["working_on"] == "M2 — parse the alarm file and write its tests."
    assert f["next"] == "M3 — email the report, then run it in Spyder."


def test_sync_pending_working_on_is_the_text_after_the_reason(tmp_path):
    work = work_project(tmp_path, log=PAUSED)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    assert fields_of(card)["working_on"] == "Draft v2 of requirements. Also open: an idea."


def test_sync_with_a_checklist_takes_working_on_and_next_from_it(tmp_path):
    work = work_project(tmp_path, files=())
    (work / "requirements.md").write_text(REQUIREMENTS, encoding="utf-8")
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    f = fields_of(card)
    assert (f["working_on"], f["next"]) == ("M3a of 5 · email the report", "M3b · schedule it")
    assert "progress" not in f          # the dashboard has no bar: "M3a of 5" already says it


def test_sync_milestone_without_a_name_is_just_its_number(tmp_path):
    work = work_project(tmp_path, files=())
    (work / "requirements.md").write_text("- [ ] M1\n- [ ] M2\n", encoding="utf-8")
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    f = fields_of(card)
    assert (f["working_on"], f["next"]) == ("M1 of 2", "M2")


def test_sync_on_the_last_milestone_or_all_done_next_comes_from_the_log(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    (work / "requirements.md").write_text("- [x] M1 — a\n- [ ] M2 — b · Done when: ok\n", encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    f = fields_of(card)
    assert (f["working_on"], f["next"]) == ("M2 of 2 · b", "M3 — email the report, then run it in Spyder.")
    (work / "requirements.md").write_text("- [x] M1 — a\n- [x] M2 — b\n", encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    f = fields_of(card)
    assert (f["working_on"], f["next"]) == ("All 2 milestones done", "M3 — email the report, then run it in Spyder.")


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


def test_sync_never_repeats_an_undated_last_update_on_a_later_day(tmp_path):
    work = work_project(tmp_path, log=LOG.replace("2026-10-22 — M1 ticked", "M1 ticked"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    pn.sync(projects(tmp_path), work, datetime(2026, 10, 24, 9, 0))
    assert [(h["date"], h["text"]) for h in history_of(card)] == [("2026-10-23", "M1 ticked, 4 tests green.")]


def test_sync_adds_a_new_history_line_on_top_when_last_update_changes(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    (work / "tracking_log.md").write_text(LOG.replace("2026-10-22 — M1 ticked, 4 tests green.",
                                                      "2026-10-23 — M2 ticked."), encoding="utf-8")
    pn.sync(projects(tmp_path), work, NOW)
    assert [h["text"] for h in history_of(card)] == ["M2 ticked.", "M1 ticked, 4 tests green."]


def test_sync_adds_every_line_of_the_newest_day_once_in_file_order(tmp_path):
    work = work_project(tmp_path, log=LOG.replace("2026-10-22 — M1 ticked, 4 tests green.",
                                                  "2026-10-23 — M2 ticked.\n2026-10-22 — M1 ticked.\n"
                                                  "2026-10-23 — M3 started."))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    pn.sync(projects(tmp_path), work, NOW)
    assert [(h["date"], h["text"]) for h in history_of(card)] == [
        ("2026-10-23", "M2 ticked."), ("2026-10-23", "M3 started.")]


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


def test_needs_sync_when_requirements_md_is_newer_than_the_card(tmp_path):
    work = work_project(tmp_path)
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    age(work / "tracking_log.md", 300)
    (work / "requirements.md").write_text(REQUIREMENTS, encoding="utf-8")
    age(work / "requirements.md", 60)
    assert not pn.needs_sync(card, work)
    age(card / "note.md", 120)              # a milestone was ticked after the card was written
    assert pn.needs_sync(card, work)


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


def test_create_refuses_to_restore_when_the_name_is_taken_by_a_plain_folder(tmp_path):
    work = work_project(tmp_path)
    notes.archive_project(projects(tmp_path), notes.new_project(projects(tmp_path), "DEMO-42"), NOW)
    (projects(tmp_path) / "DEMO-42").mkdir()                       # stray folder, no note.md
    with pytest.raises(FileExistsError):
        pn.create(projects(tmp_path), work, "", "", NOW)
    assert notes.find_archived(projects(tmp_path), "DEMO-42")      # still safe in the Archive


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


def test_archive_gone_leaves_a_card_you_restored_by_hand(tmp_path):
    wj = tmp_path / "work_jira"
    work_project(tmp_path, "DEMO-1")
    gone = work_project(tmp_path, "DEMO-2")
    pn.create(projects(tmp_path), gone, "", "", NOW)
    os.rename(gone, tmp_path / "prod_DEMO-2")
    assert pn.archive_gone(projects(tmp_path), wj, NOW) == ["DEMO-2"]
    notes.restore_project(projects(tmp_path), notes.find_archived(projects(tmp_path), "DEMO-2"), NOW)  # Restore button
    assert pn.archive_gone(projects(tmp_path), wj, NOW) == []
    assert notes.find_project(projects(tmp_path), "DEMO-2")


def test_archive_gone_again_after_a_hand_restore_once_the_folder_was_worked_on(tmp_path):
    wj = tmp_path / "work_jira"
    work_project(tmp_path, "DEMO-1")
    gone = work_project(tmp_path, "DEMO-2")
    pn.create(projects(tmp_path), gone, "", "", NOW)
    os.rename(gone, tmp_path / "prod_DEMO-2")
    pn.archive_gone(projects(tmp_path), wj, NOW)
    notes.restore_project(projects(tmp_path), notes.find_archived(projects(tmp_path), "DEMO-2"), NOW)  # Restore button
    os.rename(tmp_path / "prod_DEMO-2", gone)                       # back, and Claude works in it
    (gone / "tracking_log.md").write_text(LOG.replace("M1 ticked, 4 tests green.", "Hotfix done."), encoding="utf-8")
    pn.sync(projects(tmp_path), gone, NOW)
    os.rename(gone, tmp_path / "prod_DEMO-2")                        # and to prod again
    assert pn.archive_gone(projects(tmp_path), wj, NOW) == ["DEMO-2"]


def test_archive_gone_again_after_the_folder_came_back_and_left_again(tmp_path):
    wj = tmp_path / "work_jira"
    work_project(tmp_path, "DEMO-1")
    gone = work_project(tmp_path, "DEMO-2")
    pn.create(projects(tmp_path), gone, "", "", NOW)
    os.rename(gone, tmp_path / "prod_DEMO-2")
    pn.archive_gone(projects(tmp_path), wj, NOW)
    os.rename(tmp_path / "prod_DEMO-2", gone)                       # back from prod
    pn.create(projects(tmp_path), gone, "", "", NOW)                 # what the Stop hook does
    os.rename(gone, tmp_path / "prod_DEMO-2")                        # and to prod again
    assert pn.archive_gone(projects(tmp_path), wj, NOW) == ["DEMO-2"]


def test_archive_gone_compares_names_ignoring_case(tmp_path):
    work = work_project(tmp_path, "demo-1")
    pn.create(projects(tmp_path), work, "", "", NOW)
    os.rename(work, work.parent / "tmp")
    os.rename(work.parent / "tmp", work.parent / "DEMO-1")    # same folder on Windows
    assert pn.archive_gone(projects(tmp_path), tmp_path / "work_jira", NOW) == []


# ---------- import: a card for every work_jira folder ----------

def test_import_missing_makes_a_bare_card_for_a_folder_without_tracking_log(tmp_path):
    work = work_project(tmp_path, "boss_rpa", log=None, files=["note.md", "plan.md"])
    assert pn.import_missing(projects(tmp_path), tmp_path / "work_jira", NOW) == ["boss_rpa"]
    f = fields_of(projects(tmp_path) / "boss_rpa")
    assert (f["title"], f["status"], f["source"], f["folder"]) == ("boss_rpa", "active", "work_jira", str(work))


def test_import_missing_fills_the_card_from_tracking_log(tmp_path):
    work_project(tmp_path, "DEMO-42")
    assert pn.import_missing(projects(tmp_path), tmp_path / "work_jira", NOW) == ["DEMO-42"]
    card = projects(tmp_path) / "DEMO-42"
    assert fields_of(card)["next"].startswith("M3") and fields_of(card)["jira"] == "DEMO-42"
    assert history_of(card)[0]["text"] == "M1 ticked, 4 tests green."


def test_import_missing_skips_cards_that_exist_and_non_project_folders(tmp_path):
    wj = tmp_path / "work_jira"
    pn.create(projects(tmp_path), work_project(tmp_path, "DEMO-1"), "Mine", "", NOW)
    (wj / "_templates").mkdir()
    (wj / ".claude").mkdir()
    (wj / "readme.txt").write_text("x", encoding="utf-8")         # a file, not a folder
    assert pn.import_missing(projects(tmp_path), wj, NOW) == []
    assert {p["id"] for p in notes.list_projects(projects(tmp_path))} == {"DEMO-1"}
    assert fields_of(projects(tmp_path) / "DEMO-1")["title"] == "Mine"


def test_import_missing_never_brings_back_a_card_you_archived_yourself(tmp_path):
    work = work_project(tmp_path, "DEMO-1")
    card, _ = pn.create(projects(tmp_path), work, "", "", NOW)
    notes.archive_project(projects(tmp_path), card, NOW)            # the card's Archive button
    assert pn.import_missing(projects(tmp_path), tmp_path / "work_jira", NOW) == []
    assert notes.find_project(projects(tmp_path), "DEMO-1") is None


def test_import_missing_restores_a_card_whose_folder_came_back_from_prod(tmp_path):
    wj = tmp_path / "work_jira"
    work_project(tmp_path, "DEMO-1")
    gone = work_project(tmp_path, "DEMO-2")
    pn.create(projects(tmp_path), gone, "Two", "", NOW)
    os.rename(gone, tmp_path / "prod_DEMO-2")
    pn.archive_gone(projects(tmp_path), wj, NOW)
    pn.create(projects(tmp_path), wj / "DEMO-1", "", "", NOW)
    os.rename(tmp_path / "prod_DEMO-2", gone)                       # back from prod
    assert pn.import_missing(projects(tmp_path), wj, NOW) == ["DEMO-2"]
    assert fields_of(projects(tmp_path) / "DEMO-2")["title"] == "Two"
    assert history_of(projects(tmp_path) / "DEMO-2")[0]["text"] in (pn.BACK_FROM_PROD, "M1 ticked, 4 tests green.")


def test_import_missing_with_bad_log_headings_still_makes_a_linked_card(tmp_path):
    work = work_project(tmp_path, "DEMO-1", log="# just notes, no headings\n")
    assert pn.import_missing(projects(tmp_path), tmp_path / "work_jira", NOW) == ["DEMO-1"]
    f = fields_of(projects(tmp_path) / "DEMO-1")
    assert (f["source"], f["folder"]) == ("work_jira", str(work))
    assert pn.needs_sync(projects(tmp_path) / "DEMO-1", work)    # so the Stop hook still says what to fix


def test_import_missing_never_brings_back_a_card_you_archived_with_other_capitals(tmp_path):
    card = notes.new_project(projects(tmp_path), "DEMO-1")
    notes.archive_project(projects(tmp_path), card, NOW)
    work_project(tmp_path, "demo-1")                                # same folder on Windows
    assert pn.import_missing(projects(tmp_path), tmp_path / "work_jira", NOW) == []


def test_import_missing_skips_a_folder_when_linking_its_card_fails(tmp_path, monkeypatch):
    work_project(tmp_path, "DEMO-1", log="# just notes, no headings\n")
    work_project(tmp_path, "DEMO-2")

    def locked(card, folder):
        raise PermissionError("note.md is open in another program")
    monkeypatch.setattr(pn, "link_card", locked)
    assert pn.import_missing(projects(tmp_path), tmp_path / "work_jira", NOW) == ["DEMO-2"]


def test_import_missing_skips_a_folder_whose_card_cannot_be_made(tmp_path):
    wj = tmp_path / "work_jira"
    work_project(tmp_path, "DEMO-1")
    work_project(tmp_path, "DEMO-2")
    (projects(tmp_path) / "DEMO-1").write_text("x", encoding="utf-8")   # a stray file has the name
    assert pn.import_missing(projects(tmp_path), wj, NOW) == ["DEMO-2"]


@pytest.mark.parametrize("problem", ["missing", "not set"])
def test_import_missing_does_nothing_without_a_work_jira_folder(tmp_path, problem):
    wj = "" if problem == "not set" else tmp_path / "nowhere"
    assert pn.import_missing(projects(tmp_path), wj, NOW) == []


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
    (["create", "_templates"], "not a project folder"),
    (["create", "_archive"], "not a project folder"),
])
def test_command_errors_are_plain_english(tmp_path, capsys, args, says):
    work_project(tmp_path)
    (tmp_path / "work_jira" / "_templates").mkdir()
    (tmp_path / "work_jira" / "_archive").mkdir()
    assert pn.main(args, settings_ini(tmp_path), NOW) == 1
    assert says in capsys.readouterr().err


def test_command_without_work_jira_folder_setting_says_what_to_add(tmp_path, capsys):
    assert pn.main(["sync", "DEMO-42"], settings_ini(tmp_path, work_jira=False), NOW) == 1
    assert "work_jira_folder=" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["", "missing"])
def test_command_with_a_bad_projects_folder_says_what_to_fix(tmp_path, capsys, value, monkeypatch):
    work = work_project(tmp_path)
    ini = tmp_path / "settings.ini"
    ini.write_text(f"projects_folder={'' if value == '' else tmp_path / 'nope'}\n"
                   f"work_jira_folder={tmp_path / 'work_jira'}\n", encoding="utf-8")
    monkeypatch.chdir(work)                                          # where Claude runs it
    assert pn.main(["create", "DEMO-42"], ini, NOW) == 1
    assert "projects_folder=" in capsys.readouterr().err
    assert not (work / "DEMO-42").exists()


def test_is_project_folder(tmp_path):
    for name in ["DEMO-1", "_templates", ".claude"]:
        (tmp_path / name).mkdir()
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    assert sorted(f.name for f in tmp_path.iterdir() if pn.is_project_folder(f)) == ["DEMO-1"]


# ---------- slice 3: the app's + New project makes the work_jira folder ----------

def test_start_work_folder_makes_folder_and_ticket_md(tmp_path):
    wj = tmp_path / "work_jira"
    wj.mkdir()
    folder, made = pn.start_work_folder(wj, "ABC-123", "Line one\r\nLine two\n", " Mike ")
    assert (folder, made) == (wj / "ABC-123", True)
    assert (folder / "ticket.md").read_text(encoding="utf-8") == (
        "# ABC-123\n\nCreated by: Mike\n\n## Description (pasted from Jira)\nLine one\nLine two\n")


def test_start_work_folder_without_text_makes_an_empty_folder(tmp_path):
    (tmp_path / "work_jira").mkdir()
    folder, made = pn.start_work_folder(tmp_path / "work_jira", "beaver_reports", "", "")
    assert made and list(folder.iterdir()) == []


def test_start_work_folder_never_touches_an_existing_folder(tmp_path):
    work = work_project(tmp_path, log=LOG, files=["ticket.md"])
    before = sorted((p.name, p.read_text(encoding="utf-8")) for p in work.iterdir())
    folder, made = pn.start_work_folder(tmp_path / "work_jira", "DEMO-42", "new text", "me")
    assert (folder, made) == (work, False)
    assert sorted((p.name, p.read_text(encoding="utf-8")) for p in work.iterdir()) == before


def test_start_work_folder_needs_the_work_jira_folder_to_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        pn.start_work_folder(tmp_path / "missing", "ABC-1", "", "")
