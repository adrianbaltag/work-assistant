"""Two-way: the user's own blocker on the card (my_blocker) is never touched by the work folder sync.

The dashboard keeps the user's blocker in the card's note.md, in the --- block, as "my_blocker: ...".
Everything project_note.py and the hooks do to a card (sync, sync of all cards, the import of folders,
the automatic archive, the automatic restore) must leave that line exactly as it was.

Folders are fake (tmp_path) and all text is made up.
"""
import os

import notes
import project_note as pn
import work_jira_hooks as hooks
from test_project_note import LOG, NOW, PAUSED, fields_of, history_of, projects, work_project

MINE = "Waiting for the lab key: Dana brings it Monday"
MY_LINE = f"my_blocker: {MINE}\n"
CARD = f"""---
title: Alarm update
status: active
priority: normal
jira: DEMO-42
{MY_LINE}working_on:
next:
blocked_by:
---

## Goal
Read the alarm file every hour.

## History
- 2026-10-20 · you · Blocker: {MINE}
"""


def card_with_my_blocker(root, name="DEMO-42"):
    """A card as the dashboard leaves it after the user set a blocker (the text is written here by hand)."""
    card = projects(root) / name
    card.mkdir()
    (card / "note.md").write_text(CARD, encoding="utf-8")
    return card


def kept(card):
    """True when the user's blocker line is in the card exactly once, exactly as it was."""
    text = (card / "note.md").read_text(encoding="utf-8")
    return text.count(MY_LINE) == 1 and text.count("my_blocker") == 1 and fields_of(card)["my_blocker"] == MINE


def test_sync_keeps_the_users_blocker(tmp_path):
    work = work_project(tmp_path)
    card = card_with_my_blocker(tmp_path)

    pn.sync(tmp_path / "projects", work, NOW)

    assert kept(card)
    assert fields_of(card)["status"] == "active" and fields_of(card)["blocked_by"] == ""
    assert fields_of(card)["source"] == "work_jira" and fields_of(card)["next"].startswith("M3")


def test_sync_of_a_pending_log_keeps_the_users_blocker_next_to_the_logs_own(tmp_path):
    """Two blockers, two lines: blocked_by comes from the log (PENDING), my_blocker is the user's."""
    work = work_project(tmp_path, log=PAUSED)
    card = card_with_my_blocker(tmp_path)

    pn.sync(tmp_path / "projects", work, NOW)
    assert kept(card)
    assert fields_of(card)["status"] == "pending" and fields_of(card)["blocked_by"].startswith("waiting for the lab admin")

    (work / "tracking_log.md").write_text(LOG, encoding="utf-8")         # the log's own blocker is lifted
    pn.sync(tmp_path / "projects", work, NOW)
    assert kept(card)
    assert fields_of(card)["status"] == "active" and fields_of(card)["blocked_by"] == ""


def test_sync_all_keeps_the_users_blocker(tmp_path):
    work_project(tmp_path)
    card = card_with_my_blocker(tmp_path)

    assert pn.sync_all(tmp_path / "projects", tmp_path / "work_jira", NOW) == ["DEMO-42"]

    assert kept(card) and fields_of(card)["next"].startswith("M3")


def test_import_missing_leaves_a_card_with_the_users_blocker_alone(tmp_path):
    work_project(tmp_path)
    work_project(tmp_path, "DEMO-7")
    card = card_with_my_blocker(tmp_path)
    before = (card / "note.md").read_text(encoding="utf-8")

    assert pn.import_missing(tmp_path / "projects", tmp_path / "work_jira", NOW) == ["DEMO-7"]

    assert (card / "note.md").read_text(encoding="utf-8") == before


def test_linking_a_card_to_its_work_folder_keeps_the_users_blocker(tmp_path):
    work = work_project(tmp_path, log=None)
    card = card_with_my_blocker(tmp_path)

    pn.create(tmp_path / "projects", work, "", "", NOW)                  # no log yet: the card is only linked

    assert kept(card) and fields_of(card)["folder"] == str(work)


def test_the_automatic_archive_keeps_the_users_blocker(tmp_path):
    work_project(tmp_path, "DEMO-1")
    gone = work_project(tmp_path)
    card_with_my_blocker(tmp_path)
    pn.sync(tmp_path / "projects", gone, NOW)
    os.rename(gone, tmp_path / "prod")

    assert pn.archive_gone(tmp_path / "projects", tmp_path / "work_jira", NOW) == ["DEMO-42"]

    archived = notes.find_archived(tmp_path / "projects", "DEMO-42")
    assert kept(archived) and fields_of(archived)["status"] == "done"
    assert history_of(archived)[0]["text"] == pn.MOVED_TO_PROD


def archived_by_the_hook(tmp_path):
    """A card with the user's blocker whose folder left work_jira and came back: (the folder, the archived card)."""
    work_project(tmp_path, "DEMO-1")
    work = work_project(tmp_path)
    card_with_my_blocker(tmp_path)
    pn.sync(tmp_path / "projects", work, NOW)
    os.rename(work, tmp_path / "prod")
    pn.archive_gone(tmp_path / "projects", tmp_path / "work_jira", NOW)
    os.rename(tmp_path / "prod", work)
    return work


def test_the_automatic_restore_keeps_the_users_blocker(tmp_path):
    work = archived_by_the_hook(tmp_path)

    card, what = pn.create(tmp_path / "projects", work, "", "", NOW)

    assert what == "restored" and kept(card)
    assert fields_of(card)["status"] == "active"                         # from the log; the user's blocker is its own line


def test_import_missing_brings_the_card_back_with_the_users_blocker(tmp_path):
    archived_by_the_hook(tmp_path)

    assert "DEMO-42" in pn.import_missing(tmp_path / "projects", tmp_path / "work_jira", NOW)

    assert kept(tmp_path / "projects" / "DEMO-42")


def test_the_stop_hook_brings_the_card_back_with_the_users_blocker(tmp_path):
    work = archived_by_the_hook(tmp_path)
    settings = {"projects_folder": str(tmp_path / "projects"), "work_jira_folder": str(tmp_path / "work_jira")}

    assert hooks.stop({"cwd": str(work), "stop_hook_active": False}, settings, NOW) == (0, "")

    card = tmp_path / "projects" / "DEMO-42"
    assert kept(card) and history_of(card)[0]["text"] == pn.BACK_FROM_PROD   # the log's line was synced before


def test_a_whole_session_start_keeps_the_users_blocker(tmp_path):
    """archive check, import and sync of all cards in one go, as the SessionStart hook runs them."""
    work = work_project(tmp_path)
    card = card_with_my_blocker(tmp_path)
    settings = {"projects_folder": str(tmp_path / "projects"), "work_jira_folder": str(tmp_path / "work_jira")}

    hooks.session_start({"cwd": str(work), "source": "startup"}, settings, NOW)

    assert kept(card) and fields_of(card)["source"] == "work_jira"
