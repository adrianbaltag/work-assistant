"""The PROD_SCRIPTS folder: where ✓ Complete moves a finished ticket folder out of work_jira (Restore moves it back).

No setting holds its place. A small hidden file in it (TAG) marks it, and find() looks for that file in
Documents, Desktop and the user folder, a few levels deep. Moving the folder somewhere else moves the tag
with it, so the app still finds it. Never other drives (Z: is prod: never touched). Pure Python, no Flask.
"""
import errno
import logging
import os
import sys
from pathlib import Path

import notes

log = logging.getLogger(__name__)

TAG = ".work-assistant-completed"
TAG_TEXT = ("This file tells Work Assistant that this is your folder for completed projects.\n"
            "Please leave it here. Delete it only if you want the app to ask for the folder again.\n")
DEFAULT = Path("Documents") / "PROD_SCRIPTS"
DEPTH = 3               # levels below each place searched: home\OneDrive\Documents\PROD_SCRIPTS is 3
MAX_FOLDERS = 5000      # stop looking after this many folders (a huge user folder must not hang a click)
SKIP = {"appdata", "library", "node_modules", "__pycache__", "site-packages"}     # never hold PROD_SCRIPTS
WIN_NOT_SAME_DEVICE = 17                                                        # Windows error for another drive
WIN_HIDDEN = 0x02


def inside(path, folder):
    """True when path is folder itself or somewhere below it. Capitals count as on Windows (Path decides)."""
    try:
        Path(path).relative_to(folder)
        return True
    except ValueError:
        return False


def check_choice(typed, home, forbidden=(), extra_roots=()):
    """Is this a good place for PROD_SCRIPTS? Returns (resolved folder, "") or (None, why not, in plain words).

    It must be a whole path inside the user folder, or on work_jira's own drive when that is another drive
    (extra_roots, see work_drive). That keeps Z: and other drives out. Not one of those roots itself, not
    inside work_jira or the projects folder, no double spaces (note.md lines keep only single ones).
    It does not have to exist yet.
    """
    text = str(typed).strip()
    if not text:
        return None, "Type the folder for completed projects."
    if " ".join(text.split()) != text:
        return None, "Pick a folder whose path has no double spaces or tabs."
    folder = Path(text).expanduser()
    if not folder.is_absolute():
        return None, f"Type the whole path, like {suggestion(home)}"
    roots = [Path(home).resolve()] + [Path(r).resolve() for r in extra_roots]
    folder = folder.resolve()
    if folder in roots or not any(inside(folder, root) for root in roots):
        drives = "".join(f" or on {r}" for r in roots[1:])
        return None, f"Pick a folder inside your user folder ({roots[0]}){drives}, like {suggestion(home)}"
    for other in forbidden:
        if other and inside(folder, Path(other).resolve()):
            return None, f"That folder is inside {other}. Pick one outside it, like {suggestion(home)}"
    if folder.exists() and not folder.is_dir():
        return None, f"{folder} is a file, not a folder. Pick a folder."
    return folder, ""


def work_drive(home, work_jira, path=Path):
    """(drive root, folder holding work_jira) when work_jira is on another drive than the user folder, else
    (None, None). Then PROD_SCRIPTS may be on that drive too: a move between drives always fails.
    path: the path type (tests pass PureWindowsPath to try Windows drives on a Mac).
    """
    if not str(work_jira).strip():
        return None, None
    work, home = path(work_jira), path(home)
    if not work.drive or work.drive.casefold() == home.drive.casefold():
        return None, None
    return path(work.anchor), work.parent


def suggestion(home, near=None):
    """What the one-time box starts with: Documents\\PROD_SCRIPTS in the user folder, or next to work_jira
    when work_jira is on another drive (near)."""
    return str(Path(near) / DEFAULT.name if near else Path(home) / DEFAULT)


def find(home, forbidden=(), near=None, extra_roots=()):
    """The folder that holds TAG, or None. Searches Documents, Desktop, the rest of the user folder, then near
    (the folder holding work_jira, when that is on another drive).

    Skips hidden folders, AppData and the like, links, and any folder it can't read. A tagged folder that
    check_choice would refuse (inside work_jira, say) does not count. Stops after MAX_FOLDERS folders.
    """
    home = Path(home)
    left = MAX_FOLDERS
    for root in [home / "Documents", home / "Desktop", home] + ([Path(near)] if near else []):
        # Documents\x\y and home\a\b\c are both 3 levels below home. Home's own Documents/Desktop: done already.
        level = [root] if root != home else children(home, skip={"documents", "desktop"})
        for depth in range(DEPTH):
            for folder in level:
                if left <= 0:
                    log.warning("Looked in %s folders for %s and stopped: not found", MAX_FOLDERS, TAG)
                    return None
                left -= 1
                if has_tag(folder) and check_choice(folder, home, forbidden, extra_roots)[0]:
                    return folder
            if depth < DEPTH - 1:
                level = deeper(level, left)
    return None


def deeper(level, most):
    """The sub-folders of every folder in level, at most `most` of them (no need to list more than we check)."""
    found = []
    for folder in level:
        if len(found) >= most:
            break
        found += children(folder)
    return found[:most]


def has_tag(folder):
    """True when the folder holds TAG. A folder we may not look into counts as no."""
    try:
        return (Path(folder) / TAG).is_file()
    except OSError as err:
        log.debug("Could not look for %s in %s (%s)", TAG, folder, err)
        return False


def children(folder, skip=()):
    """The sub-folders worth searching (no hidden, no links, no AppData ...). A folder that can't be read = none."""
    try:
        with os.scandir(folder) as entries:
            return sorted((Path(e.path) for e in entries
                           if e.is_dir(follow_symlinks=False) and not e.name.startswith(".")
                           and e.name.casefold() not in SKIP and e.name.casefold() not in skip), key=notes.by_name)
    except OSError as err:          # e.g. Windows "My Music" links: debug only, or every pop-up fills the log
        log.debug("Could not look inside %s (%s)", folder, err)
        return []


def make(folder):
    """Make the folder (and its parents) if missing, and put the tag file in it if it has none."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tag = folder / TAG
    if not tag.exists():
        tag.write_text(TAG_TEXT, encoding="utf-8")
        hide(tag)


def hide(file):
    """Windows: set the hidden mark (a dot in the name hides it only on a Mac). Failing is fine: it still works."""
    if sys.platform == "win32":
        import ctypes
        if not ctypes.windll.kernel32.SetFileAttributesW(str(file), WIN_HIDDEN):
            log.warning("Could not hide %s (it still works, it just shows)", file)


def move_out(work_folder, prod, now):
    """Move a ticket folder into PROD_SCRIPTS. A taken name gets the date: "ABC-1 (2026-11-21 14-05)". Returns where.

    A plain rename: all or nothing. On another drive it fails (other_drive) instead of copying half a folder.
    """
    name = " ".join(Path(work_folder).name.split())      # single spaces: the card's prod_folder: line keeps only those
    target = notes.free_name(prod, name, now, folder=True)
    os.rename(work_folder, target)
    return target


def other_drive(err):
    """True when a move failed because the two folders are on different drives."""
    return getattr(err, "winerror", None) == WIN_NOT_SAME_DEVICE or err.errno == errno.EXDEV
