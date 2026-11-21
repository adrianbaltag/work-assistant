"""Folder and file names come in the same order on the Mac and on Windows: A-Z, capitals don't count.

Found in the Windows check: Python sorts paths with capitals first on the Mac (DEMO-1, boss_rpa)
and without looking at capitals on Windows (boss_rpa, DEMO-1). The app now always does the second.
"""
import os

import notes
import project_note as pn
from test_notes import make_project
from test_project_note import NOW, projects, work_project
from test_sync_stamp import stale_card


def test_project_folders_are_listed_a_to_z_ignoring_capitals(tmp_path):
    for name in ("Zeta-1", "boss_rpa", "DEMO-1"):
        make_project(tmp_path, name)
    assert [f.name for f in notes.project_folders(tmp_path)] == ["boss_rpa", "DEMO-1", "Zeta-1"]


def test_new_cards_are_named_a_to_z_ignoring_capitals(tmp_path):
    for name in ("Zeta-1", "boss_rpa", "DEMO-1"):
        work_project(tmp_path, name)
    added = pn.import_missing(projects(tmp_path), tmp_path / "work_jira", NOW)
    assert added == ["boss_rpa", "DEMO-1", "Zeta-1"]


def test_synced_cards_are_named_a_to_z_ignoring_capitals(tmp_path):
    for name in ("Zeta-1", "boss_rpa", "DEMO-1"):
        stale_card(tmp_path, name)
    synced = pn.sync_all(projects(tmp_path), tmp_path / "work_jira", NOW)
    assert synced == ["boss_rpa", "DEMO-1", "Zeta-1"]


def test_archived_cards_are_named_a_to_z_ignoring_capitals(tmp_path):
    work_project(tmp_path, "KEEP-1")                              # work_jira is not empty, so the check runs
    for name in ("Zeta-1", "boss_rpa", "DEMO-1"):
        gone = work_project(tmp_path, name)
        pn.create(projects(tmp_path), gone, "", "", NOW)
        os.rename(gone, tmp_path / ("prod_" + name))              # moved to prod
    archived = pn.archive_gone(projects(tmp_path), tmp_path / "work_jira", NOW)
    assert archived == ["boss_rpa", "DEMO-1", "Zeta-1"]


def test_a_projects_files_are_listed_z_to_a_ignoring_capitals(tmp_path):
    """Newest name first (the names start with a date), so the order is Z to A."""
    project = make_project(tmp_path, "P")
    (project / "raw").mkdir()
    for name in ("a.txt", "C.txt", "b.txt"):
        (project / "raw" / name).write_text("x", encoding="utf-8")
    names = [f["name"] for f in notes.list_files(project)["raw"]]
    assert names == ["C.txt", "b.txt", "a.txt"]
