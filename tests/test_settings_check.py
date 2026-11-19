"""S4: one settings check (app.validate_settings) shared by the app start-up and check_setup.py,
and a lowercase work_jira folder (abc-123) gets its Jira button.

All folders are fake (tmp_path) and all IDs are made up.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

import app as app_module
import check_setup
import notes
import project_note as pn

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 18, 9, 30)


def write_ini(tmp_path, body):
    path = tmp_path / "settings.ini"
    path.write_text(body, encoding="utf-8")
    return path


def bad_texts(findings, only_stops=False):
    return [f.text for f in findings if f.level == "bad" and (f.stops_app or not only_stops)]


def start_message(tmp_path, monkeypatch, body):
    """The text a person sees when the app is started with this settings.ini (None = it started)."""
    ini = write_ini(tmp_path, body)
    monkeypatch.setattr(app_module, "load_settings", lambda *a: notes.load_settings(ini))
    with pytest.raises(SystemExit) as stop:
        app_module.create_app()
    return str(stop.value)


# ---------- load_settings: a line it cannot read ----------

def test_a_line_that_is_not_key_value_stops_with_its_line_number(tmp_path):
    ini = write_ini(tmp_path, "jira_url=https://jira.example.com\nmy projects folder\n")
    with pytest.raises(SystemExit) as stop:
        notes.load_settings(ini)
    message = str(stop.value)
    assert str(ini) in message and "line 2" in message and "my projects folder" in message


def test_a_key_written_twice_stops_with_its_line_number(tmp_path):
    with pytest.raises(SystemExit, match="jira_url= twice"):
        notes.load_settings(write_ini(tmp_path, "jira_url=a\njira_url=b\n"))


def test_a_settings_file_that_is_not_text_stops_with_a_plain_message(tmp_path):
    ini = tmp_path / "settings.ini"
    ini.write_bytes(b"projects_folder=\xff\xfe\x00\x80\n")
    with pytest.raises(SystemExit, match="UTF-8"):
        notes.load_settings(ini)


# ---------- validate_settings ----------

def test_validate_good_settings_has_no_bad_finding(tmp_path):
    (tmp_path / "p").mkdir()
    ini = write_ini(tmp_path, f"projects_folder={tmp_path / 'p'}\n")
    settings, slack, findings = app_module.validate_settings(ini)
    assert bad_texts(findings) == [] and settings["projects_folder"] == str(tmp_path / "p")
    assert slack["mode"] == "instant"


def test_validate_reports_every_mistake_not_just_the_first(tmp_path):
    ini = write_ini(tmp_path, f"projects_folder={tmp_path / 'nope'}\ntext_limit=lots\nslack_mode=fast\n")
    _, _, findings = app_module.validate_settings(ini)
    text = "\n".join(bad_texts(findings))
    assert "does not exist" in text and "whole number of characters" in text and "instant or backup" in text


def test_validate_with_no_file_returns_one_bad_finding(tmp_path):
    settings, _, findings = app_module.validate_settings(tmp_path / "settings.ini")
    assert settings is None and len(bad_texts(findings)) == 1
    assert "settings.ini.example" in bad_texts(findings)[0]


def test_validate_with_an_unreadable_line_returns_one_bad_finding(tmp_path):
    settings, _, findings = app_module.validate_settings(write_ini(tmp_path, "oops\n"))
    assert settings is None and "line 1" in bad_texts(findings)[0]


def test_a_missing_work_jira_folder_is_bad_for_check_setup_but_does_not_stop_the_app(tmp_path):
    (tmp_path / "p").mkdir()
    ini = write_ini(tmp_path, f"projects_folder={tmp_path / 'p'}\nwork_jira_folder={tmp_path / 'nope'}\n")
    _, _, findings = app_module.validate_settings(ini)
    assert bad_texts(findings) and bad_texts(findings, only_stops=True) == []


# ---------- the app start-up: a short plain message, never a traceback ----------

def test_start_with_projects_folder_missing(tmp_path, monkeypatch):
    message = start_message(tmp_path, monkeypatch, "jira_url=https://jira.example.com\n")
    assert "projects_folder=" in message and "settings.ini" in message and "Traceback" not in message


def test_start_with_projects_folder_that_does_not_exist_still_starts(tmp_path, monkeypatch):
    """Decided 2026-11-18: a folder that is away (no VPN) does not stop the start; the page shows the message."""
    ini = write_ini(tmp_path, f"projects_folder={tmp_path / 'nope'}\nslack_mode=backup\n")
    monkeypatch.setattr(app_module, "load_settings", lambda *a: notes.load_settings(ini))
    monkeypatch.setattr(app_module.slack_live, "start", lambda settings, inbox: None)
    page = app_module.create_app().test_client().get("/api/projects")
    assert page.status_code == 500 and str(tmp_path / "nope") in page.json["error"]


def test_start_with_a_line_that_is_not_key_value(tmp_path, monkeypatch):
    message = start_message(tmp_path, monkeypatch, "my projects folder\n")
    assert "line 1" in message and "my projects folder" in message


def test_start_with_a_bad_number(tmp_path, monkeypatch):
    (tmp_path / "p").mkdir()
    message = start_message(tmp_path, monkeypatch, f"projects_folder={tmp_path / 'p'}\ntext_limit=200,000\n")
    assert "text_limit=" in message and "whole number" in message


def test_start_names_every_mistake_at_once(tmp_path, monkeypatch):
    message = start_message(tmp_path, monkeypatch,
                            f"projects_folder={tmp_path / 'nope'}\ntext_limit=lots\nslack_poll_seconds=1\n")
    assert "text_limit=" in message and "slack_poll_seconds=" in message
    assert "does not exist" not in message      # the folder that is away is not what stops the start


def test_start_with_no_settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "load_settings", lambda *a: notes.load_settings(tmp_path / "settings.ini"))
    with pytest.raises(SystemExit, match="settings.ini.example"):
        app_module.create_app()


def test_start_with_a_missing_work_jira_folder_still_starts(tmp_path, monkeypatch):
    (tmp_path / "p").mkdir()
    ini = write_ini(tmp_path, f"projects_folder={tmp_path / 'p'}\nwork_jira_folder={tmp_path / 'nope'}\n"
                              "slack_mode=backup\n")
    monkeypatch.setattr(app_module, "load_settings", lambda *a: notes.load_settings(ini))
    monkeypatch.setattr(app_module.slack_live, "start", lambda settings, inbox: None)
    assert app_module.create_app() is not None


def test_a_real_start_ends_with_the_message_and_no_traceback(tmp_path):
    """The whole thing in a real Python: exit code 1, the words on stderr, no 'Traceback'."""
    ini = write_ini(tmp_path, "my projects folder\n")
    code = ("import sys, notes, app; app.load_settings = lambda *a: notes.load_settings(sys.argv[1]); "
            "app.create_app()")
    done = subprocess.run([sys.executable, "-c", code, str(ini)], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 1 and "line 1" in done.stderr and "Traceback" not in done.stderr


# ---------- check_setup.py says the same, in its own style ----------

def test_check_setup_shows_the_same_findings_as_validate_settings(tmp_path):
    ini = write_ini(tmp_path, f"projects_folder={tmp_path / 'nope'}\ntext_limit=lots\n")
    _, _, findings = app_module.validate_settings(ini)
    lines, _, _ = check_setup.check_settings(ini)
    shown = [text for mark, text in lines if mark == check_setup.BAD]
    assert shown == bad_texts(findings)


def test_check_setup_keeps_the_ok_skip_and_warn_lines(tmp_path):
    (tmp_path / "p").mkdir()
    ini = write_ini(tmp_path, f"projects_folder={tmp_path / 'p'}\njira_url=jira.example.com\n")
    lines, _, _ = check_setup.check_settings(ini)
    assert [mark for mark, _ in lines] == [check_setup.OK, check_setup.OK, check_setup.SKIP, check_setup.WARN]


# ---------- lowercase ticket folders ----------

def work_folder(tmp_path, name):
    folder = tmp_path / "work_jira" / name
    folder.mkdir(parents=True)
    return folder


def card_fields(tmp_path, name):
    return notes.parse_note((tmp_path / "projects" / name / notes.NOTE_FILE).read_text(encoding="utf-8"))[0]


@pytest.fixture
def projects(tmp_path):
    (tmp_path / "projects").mkdir()
    return tmp_path / "projects"


def test_import_of_a_lowercase_ticket_folder_fills_jira_in_capitals(tmp_path, projects):
    work_folder(tmp_path, "abc-123")
    assert pn.import_missing(projects, tmp_path / "work_jira", NOW) == ["abc-123"]
    assert card_fields(tmp_path, "abc-123")["jira"] == "ABC-123"
    assert [f.name for f in (tmp_path / "work_jira").iterdir()] == ["abc-123"]     # nothing renamed
    assert [f.name for f in projects.iterdir()] == ["abc-123"]


def test_import_of_a_mixed_case_ticket_folder_fills_jira_in_capitals(tmp_path, projects):
    work_folder(tmp_path, "Net5g-42")
    pn.import_missing(projects, tmp_path / "work_jira", NOW)
    assert card_fields(tmp_path, "Net5g-42")["jira"] == "NET5G-42"


def test_import_of_a_capital_ticket_folder_still_fills_jira(tmp_path, projects):
    work_folder(tmp_path, "ABC-123")
    pn.import_missing(projects, tmp_path / "work_jira", NOW)
    assert card_fields(tmp_path, "ABC-123")["jira"] == "ABC-123"


@pytest.mark.parametrize("name", ["my_idea", "abc123", "abc-", "123-abc"])
def test_import_of_a_folder_that_is_not_a_ticket_leaves_jira_empty(tmp_path, projects, name):
    work_folder(tmp_path, name)
    pn.import_missing(projects, tmp_path / "work_jira", NOW)
    assert card_fields(tmp_path, name)["jira"] == ""


def test_a_card_already_imported_in_lowercase_gets_jira_when_create_runs_again(tmp_path, projects):
    folder = work_folder(tmp_path, "abc-123")
    notes.new_project(projects, "abc-123")                 # what the old import made: jira: empty
    assert card_fields(tmp_path, "abc-123")["jira"] == ""
    assert pn.create(projects, folder, "", "", NOW)[1] == "exists"
    assert card_fields(tmp_path, "abc-123")["jira"] == "ABC-123"


def test_create_never_changes_a_jira_value_someone_typed(tmp_path, projects):
    folder = work_folder(tmp_path, "abc-123")
    card = notes.new_project(projects, "abc-123")
    note = card / notes.NOTE_FILE
    note.write_text(notes.set_fields(note.read_text(encoding="utf-8"), {"jira": "OTHER-9"}), encoding="utf-8")
    pn.create(projects, folder, "", "", NOW)
    assert card_fields(tmp_path, "abc-123")["jira"] == "OTHER-9"
