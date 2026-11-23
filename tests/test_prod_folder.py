"""G3: finding and checking the PROD_SCRIPTS folder (where ✓ Complete moves a ticket folder).
Fake home folders only (tmp_path), never the real one."""
import errno
import os
import stat
import sys
from datetime import datetime

import pytest

import prod_folder


@pytest.fixture
def home(tmp_path):
    folder = tmp_path / "home"
    (folder / "Documents").mkdir(parents=True)
    (folder / "Desktop").mkdir()
    return folder


def tagged(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / prod_folder.TAG).write_text("x", encoding="utf-8")
    return folder


# ---------- find ----------

def test_no_tag_file_anywhere_finds_nothing(home):
    assert prod_folder.find(home) is None


def test_finds_the_tagged_folder_in_documents(home):
    target = tagged(home / "Documents" / "PROD_SCRIPTS")
    assert prod_folder.find(home) == target


def test_finds_it_a_few_levels_down_in_the_user_folder(home):
    target = tagged(home / "OneDrive" / "Documents" / "PROD_SCRIPTS")       # 3 levels below home
    assert prod_folder.find(home) == target


def test_too_deep_is_not_searched(home):
    tagged(home / "a" / "b" / "c" / "d")                                    # 4 levels below home
    assert prod_folder.find(home) is None


def test_documents_wins_over_desktop_and_the_user_folder(home):
    tagged(home / "Desktop" / "old")
    tagged(home / "x" / "other")
    target = tagged(home / "Documents" / "PROD_SCRIPTS")
    assert prod_folder.find(home) == target


def test_hidden_and_appdata_folders_are_skipped(home):
    tagged(home / ".cache" / "p")
    tagged(home / "AppData" / "p")
    tagged(home / "Library" / "p")
    assert prod_folder.find(home) is None


def test_a_folder_named_like_the_tag_does_not_count(home):
    (home / "Documents" / "P" / prod_folder.TAG).mkdir(parents=True)
    assert prod_folder.find(home) is None


def test_a_tagged_folder_inside_work_jira_or_projects_is_ignored(home):
    tagged(home / "Desktop" / "work_jira" / "P")
    target = tagged(home / "x" / "PROD")
    assert prod_folder.find(home, forbidden=[home / "Desktop" / "work_jira"]) == target


def test_a_folder_that_cannot_be_read_is_skipped(home, monkeypatch):
    target = tagged(home / "Desktop" / "PROD")
    real = prod_folder.os.scandir
    def locked(path):
        if str(path).endswith("Documents"):
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)
    monkeypatch.setattr(prod_folder.os, "scandir", locked)
    assert prod_folder.find(home) == target


def test_suggestion_is_documents_prod_scripts(home):
    assert prod_folder.suggestion(home) == str(home / "Documents" / "PROD_SCRIPTS")


# ---------- check what was typed in the box ----------

@pytest.mark.parametrize("typed", ["Documents/PROD_SCRIPTS", "PROD_SCRIPTS", "   "])
def test_box_needs_a_whole_path(home, typed):
    folder, why = prod_folder.check_choice(typed, home)
    assert folder is None and why


def test_box_accepts_a_folder_in_the_user_folder_even_if_it_is_not_there_yet(home):
    folder, why = prod_folder.check_choice(f"  {home / 'Documents' / 'PROD_SCRIPTS'}  ", home)
    assert (folder, why) == ((home / "Documents" / "PROD_SCRIPTS").resolve(), "")


def test_box_refuses_outside_the_user_folder_and_the_user_folder_itself(home, tmp_path):
    for typed in (tmp_path / "elsewhere", home, home / ".." / "home2"):
        folder, why = prod_folder.check_choice(str(typed), home)
        assert folder is None and "user folder" in why


def test_box_refuses_work_jira_and_the_projects_folder_and_inside_them(home):
    work, projects = home / "Desktop" / "work_jira", home / "Desktop" / "projects"
    for typed in (work, work / "PROD", projects / "PROD"):
        folder, why = prod_folder.check_choice(str(typed), home, forbidden=[work, projects])
        assert folder is None and "inside" in why


def test_box_refuses_a_file(home):
    file = home / "Documents" / "notes.txt"
    file.write_text("x", encoding="utf-8")
    folder, why = prod_folder.check_choice(str(file), home)
    assert folder is None and "file" in why


# ---------- make it, move into it ----------

def test_make_creates_the_folder_and_the_tag_once(home):
    target = home / "Documents" / "PROD_SCRIPTS"
    prod_folder.make(target)
    tag = target / prod_folder.TAG
    assert tag.is_file() and "Work Assistant" in tag.read_text(encoding="utf-8")
    tag.unlink()                                    # Windows won't overwrite a hidden file, so delete it first
    tag.write_text("kept", encoding="utf-8")
    prod_folder.make(target)                                                # second time: tag left alone
    assert tag.read_text(encoding="utf-8") == "kept"
    assert prod_folder.find(home) == target


@pytest.mark.skipif(sys.platform != "win32", reason="the hidden mark exists only on Windows")
def test_make_hides_the_tag_on_windows(home):
    target = home / "Documents" / "PROD_SCRIPTS"
    prod_folder.make(target)
    attributes = os.stat(target / prod_folder.TAG).st_file_attributes
    assert attributes & stat.FILE_ATTRIBUTE_HIDDEN


def test_move_out_keeps_the_name_or_adds_the_date_when_taken(home, tmp_path):
    prod = tagged(home / "Documents" / "PROD_SCRIPTS")
    work = tmp_path / "work_jira"
    (work / "ABC-1").mkdir(parents=True)
    (work / "ABC-1" / "x.py").write_text("x", encoding="utf-8")

    first = prod_folder.move_out(work / "ABC-1", prod, datetime(2026, 11, 21, 14, 5))

    assert first == prod / "ABC-1" and (first / "x.py").is_file() and not (work / "ABC-1").exists()
    (work / "ABC-1").mkdir()
    second = prod_folder.move_out(work / "ABC-1", prod, datetime(2026, 11, 21, 14, 5))
    assert second == prod / "ABC-1 (2026-11-21 14-05)"


def test_other_drive_is_told_apart(home):
    assert prod_folder.other_drive(OSError(errno.EXDEV, "Invalid cross-device link"))
    err = OSError(errno.EINVAL, "x")
    err.winerror = 17                                                       # Windows: not the same device
    assert prod_folder.other_drive(err)
    assert not prod_folder.other_drive(PermissionError(13, "denied"))


# ---------- review round 1 ----------

def test_a_tag_check_that_is_refused_counts_as_not_found(home, monkeypatch):
    target = tagged(home / "Desktop" / "PROD")
    real = prod_folder.Path.is_file
    def guarded(self):
        if self.parent.name == "Documents":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self)
    monkeypatch.setattr(prod_folder.Path, "is_file", guarded)
    assert prod_folder.find(home) == target


def test_the_search_stops_after_max_folders(home, monkeypatch):
    for i in range(30):
        (home / f"f{i:02}" / "sub").mkdir(parents=True)
    tagged(home / "f29" / "sub" / "PROD")
    looked = []
    real = prod_folder.Path.is_file
    def counting(self):
        looked.append(self)
        return real(self)
    monkeypatch.setattr(prod_folder.Path, "is_file", counting)
    monkeypatch.setattr(prod_folder, "MAX_FOLDERS", 10)

    assert prod_folder.find(home) is None
    assert len(looked) <= 10                       # stopped at the limit, not after all 30 folders of a level


def test_box_refuses_double_spaces_and_tabs_in_the_path(home):
    for typed in (home / "My  Stuff", home / "My\tStuff"):
        folder, why = prod_folder.check_choice(str(typed), home)
        assert folder is None and "space" in why


def test_move_out_makes_double_spaces_in_the_name_single(home, tmp_path):
    prod = tagged(home / "Documents" / "PROD_SCRIPTS")
    (tmp_path / "w" / "ABC-1  hotfix").mkdir(parents=True)
    moved = prod_folder.move_out(tmp_path / "w" / "ABC-1  hotfix", prod, datetime(2026, 11, 21, 14, 5))
    assert moved == prod / "ABC-1 hotfix"


def test_work_jira_on_another_drive_is_allowed_and_suggested(home, tmp_path):
    drive = tmp_path / "D-drive"                               # stands in for D:\ (work_jira's drive)
    work = drive / "work_jira"
    work.mkdir(parents=True)
    folder, why = prod_folder.check_choice(str(drive / "PROD_SCRIPTS"), home, forbidden=[work], extra_roots=[drive])
    assert (folder, why) == ((drive / "PROD_SCRIPTS").resolve(), "")
    folder, why = prod_folder.check_choice(str(tmp_path / "elsewhere"), home, extra_roots=[drive])
    assert folder is None and str(drive) in why
    assert prod_folder.suggestion(home, near=drive) == str(drive / "PROD_SCRIPTS")
    target = tagged(drive / "PROD_SCRIPTS")
    assert prod_folder.find(home, forbidden=[work], near=drive, extra_roots=[drive]) == target


def test_work_drive_only_when_work_jira_is_on_another_drive():
    from pathlib import PureWindowsPath as W
    assert prod_folder.work_drive(W(r"C:\Users\me"), r"D:\work_jira", W) == (W("D:\\"), W("D:\\"))
    assert prod_folder.work_drive(W(r"C:\Users\me"), r"D:\jobs\work_jira", W) == (W("D:\\"), W(r"D:\jobs"))
    assert prod_folder.work_drive(W(r"C:\Users\me"), r"c:\Users\me\Desktop\work_jira", W) == (None, None)
    assert prod_folder.work_drive(W(r"C:\Users\me"), "", W) == (None, None)
