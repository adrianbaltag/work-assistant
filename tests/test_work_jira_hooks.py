"""work_jira sync, slice 2: work_jira_hooks.py (the Stop and SessionStart hooks).

Hook input is fake JSON, folders are fake (tmp_path), all text is made up.
"""
import io
import json
import os
from datetime import datetime

import notes
import project_note as pn
import work_jira_hooks as hooks
from test_project_note import LOG, age, fields_of, history_of, work_project

NOW = datetime(2026, 10, 23, 9, 30)


def setup(tmp_path):
    """settings dict + the projects folder, like settings.ini at work."""
    projects = tmp_path / "projects"
    projects.mkdir()
    (tmp_path / "work_jira").mkdir(exist_ok=True)
    return {"projects_folder": str(projects), "work_jira_folder": str(tmp_path / "work_jira")}, projects


def stop(settings, cwd, active=False):
    return hooks.stop({"cwd": str(cwd), "stop_hook_active": active}, settings, NOW)


# ---------- Stop hook ----------

def test_stop_outside_work_jira_does_nothing(tmp_path):
    settings, _ = setup(tmp_path)
    assert stop(settings, tmp_path) == (0, "")
    assert stop({**settings, "work_jira_folder": ""}, tmp_path / "work_jira") == (0, "")


def test_stop_during_setup_does_nothing(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path, log=None, files=["ticket.md"])
    assert stop(settings, work) == (0, "")
    assert list(projects.iterdir()) == []


def test_stop_asks_claude_once_to_create_the_card(tmp_path):
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path)
    code, message = stop(settings, work / "tests")
    assert code == 2
    assert "project_note.py" in message and "create DEMO-42" in message and "--goal" in message
    assert stop(settings, work, active=True) == (0, "")         # never loops


def test_stop_syncs_a_stale_card_without_claude(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path)
    card = notes.new_project(projects, "DEMO-42")
    age(card / "note.md", 60)
    assert stop(settings, work) == (0, "")
    assert fields_of(card)["next"].startswith("M3") and fields_of(card)["source"] == "work_jira"


def test_stop_leaves_an_up_to_date_card_alone(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path)
    card = notes.new_project(projects, "DEMO-42")
    before = (card / "note.md").read_text(encoding="utf-8")
    assert stop(settings, work) == (0, "")
    assert (card / "note.md").read_text(encoding="utf-8") == before


def test_stop_with_bad_log_headings_asks_claude_once(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path, log="## Now working on\nx\n")
    card = notes.new_project(projects, "DEMO-42")
    age(card / "note.md", 60)
    code, message = stop(settings, work)
    assert code == 2 and "## Next up" in message
    assert stop(settings, work, active=True) == (0, "")


def test_stop_brings_an_archived_card_back_without_claude(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path)
    notes.archive_project(projects, notes.new_project(projects, "DEMO-42"), NOW)
    assert stop(settings, work) == (0, "")
    card = projects / "DEMO-42"
    assert fields_of(card)["status"] == "active" and fields_of(card)["next"].startswith("M3")


def test_stop_in_the_whole_work_jira_folder_syncs_cards_but_never_asks(tmp_path):
    settings, projects = setup(tmp_path)
    synced = work_project(tmp_path, "DEMO-1")
    work_project(tmp_path, "DEMO-2")                       # old project, no card: no nagging
    card = notes.new_project(projects, "DEMO-1")
    age(card / "note.md", 60)
    assert stop(settings, tmp_path / "work_jira") == (0, "")
    assert fields_of(card)["next"].startswith("M3")
    assert notes.find_project(projects, "DEMO-2") is None


# ---------- SessionStart hook ----------

def start(settings, cwd):
    return hooks.session_start({"cwd": str(cwd), "source": "startup"}, settings, NOW)


def test_session_start_archives_cards_whose_folder_left(tmp_path):
    settings, projects = setup(tmp_path)
    work_project(tmp_path, "DEMO-1")
    gone = work_project(tmp_path, "DEMO-2")
    pn.create(projects, gone, "", "", NOW)
    os.rename(gone, tmp_path / "prod")
    context, for_user = start(settings, tmp_path)
    assert "DEMO-2" in for_user and "Archive" in for_user
    assert notes.find_archived(projects, "DEMO-2") and history_of(notes.find_archived(projects, "DEMO-2"))[0]["text"] == pn.MOVED_TO_PROD


def test_session_start_in_a_new_folder_asks_for_full_setup(tmp_path):
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path, log=None, files=["ticket.md"])
    context, for_user = start(settings, work)
    assert "new project folder" in context and "_templates" in context
    assert "ticket.md" in context and "clear-requirements" in context and "grill-me" in context
    assert for_user == ""


def test_session_start_in_an_old_folder_builds_missing_md_without_grilling(tmp_path):
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path, "beaver_reports", log=None, files=["notes.md", "query.sql"])
    context, _ = start(settings, work)
    assert "missing its md set" in context and "already in the folder" in context
    assert "Do not run clear-requirements or grill-me" in context


def test_session_start_in_a_set_up_folder_or_elsewhere_says_nothing(tmp_path):
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path)
    assert start(settings, work) == ("", "")
    assert start(settings, tmp_path) == ("", "")


# ---------- main: reading hook input, printing, exit codes ----------

def write_ini(tmp_path, settings):
    ini = tmp_path / "settings.ini"
    ini.write_text("".join(f"{k}={v}\n" for k, v in settings.items()), encoding="utf-8")
    return ini


def test_main_stop_block_goes_to_stderr_with_exit_2(tmp_path, capsys):
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path)
    stdin = io.StringIO(json.dumps({"cwd": str(work), "stop_hook_active": False}))
    assert hooks.main(["stop"], stdin, write_ini(tmp_path, settings), NOW) == 2
    assert "create DEMO-42" in capsys.readouterr().err


def test_main_session_start_prints_hook_json(tmp_path, capsys):
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path, log=None)
    stdin = io.StringIO(json.dumps({"cwd": str(work), "source": "startup"}))
    assert hooks.main(["session-start"], stdin, write_ini(tmp_path, settings), NOW) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "new project folder" in out["hookSpecificOutput"]["additionalContext"]
    assert "systemMessage" not in out


def test_main_prints_nothing_when_there_is_nothing_to_say(tmp_path, capsys):
    settings, _ = setup(tmp_path)
    stdin = io.StringIO(json.dumps({"cwd": str(tmp_path), "source": "startup"}))
    assert hooks.main(["session-start"], stdin, write_ini(tmp_path, settings), NOW) == 0
    assert capsys.readouterr().out == ""


def test_main_problems_never_block_claude(tmp_path, capsys):
    stdin = io.StringIO(json.dumps({"cwd": str(tmp_path)}))
    assert hooks.main(["stop"], stdin, tmp_path / "missing.ini", NOW) == 1      # exit 1 = shown, not blocking
    assert "settings.ini" in capsys.readouterr().err
    assert hooks.main(["stop"], io.StringIO("not json"), write_ini(tmp_path, setup(tmp_path)[0]), NOW) == 0
