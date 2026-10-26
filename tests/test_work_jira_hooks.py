"""work_jira sync, slice 2: work_jira_hooks.py (the Stop and SessionStart hooks).

Hook input is fake JSON, folders are fake (tmp_path), all text is made up.
"""
import io
import json
import os
from contextlib import redirect_stderr
from datetime import datetime

import pytest
from pathlib import Path, PureWindowsPath

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


def settings_ini(tmp_path, settings):
    ini = tmp_path / "settings.ini"
    ini.write_text("".join(f"{k}={v}\n" for k, v in settings.items()), encoding="utf-8")
    return ini


def stop(settings, cwd, active=False):
    return hooks.stop({"cwd": str(cwd), "stop_hook_active": active, "session_id": SESSION}, settings, NOW)


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



def test_command_paths_for_claude_use_forward_slashes():
    """Git Bash eats backslashes; PowerShell, Git Bash and cmd all accept C:/Users/... ."""
    assert hooks.quoted(PureWindowsPath(r"C:\Users\demo\work-assistant\.venv\Scripts\python.exe")) == \
        "C:/Users/demo/work-assistant/.venv/Scripts/python.exe"
    assert hooks.quoted(PureWindowsPath(r"C:\Users\Demo Person\project_note.py")) == '"C:/Users/Demo Person/project_note.py"'


def test_create_card_command_with_a_space_in_the_path_says_how_to_run_it_in_powershell(tmp_path, monkeypatch):
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path)
    monkeypatch.setattr(hooks.sys, "executable", str(tmp_path / "Demo Person" / "python.exe"))
    _, message = stop(settings, work)
    assert "PowerShell" in message and "&" in message
    monkeypatch.setattr(hooks, "HELPER", tmp_path / "project_note.py")
    monkeypatch.setattr(hooks.sys, "executable", str(tmp_path / "python.exe"))
    _, message = stop(settings, work)
    assert "PowerShell" not in message

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


def test_stop_brings_a_card_back_when_its_folder_came_back_from_prod(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path)
    notes.archive_project(projects, notes.new_project(projects, "DEMO-42"), NOW, said=pn.MOVED_TO_PROD)
    assert stop(settings, work) == (0, "")
    card = projects / "DEMO-42"
    assert fields_of(card)["status"] == "active" and fields_of(card)["next"].startswith("M3")
    assert history_of(card)[1]["text"] == pn.BACK_FROM_PROD       # [0] = the Last update line from the log


def test_stop_leaves_a_card_you_archived_yourself_in_the_archive(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path)
    notes.archive_project(projects, notes.new_project(projects, "DEMO-42"), NOW)    # Mark done & archive
    assert stop(settings, work) == (0, "")                          # no card, and no asking Claude for one
    assert notes.find_project(projects, "DEMO-42") is None and notes.find_archived(projects, "DEMO-42")


@pytest.mark.parametrize("value", ["", "missing"])
def test_hooks_with_a_bad_projects_folder_stop_with_a_plain_message(tmp_path, value):
    settings, _ = setup(tmp_path)
    settings["projects_folder"] = "" if value == "" else str(tmp_path / "nope")
    work = work_project(tmp_path)
    for which in ("stop", "session-start"):
        err = io.StringIO()
        with redirect_stderr(err):
            code = hooks.main([which], io.StringIO(json.dumps({"cwd": str(work)})), settings_ini(tmp_path, settings))
        assert code == 1 and "projects_folder=" in err.getvalue()
    assert not (work / "DEMO-42").exists() and not (work / "_archive").exists()


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


def test_session_start_adds_cards_for_folders_without_one(tmp_path):
    settings, projects = setup(tmp_path)
    work_project(tmp_path, "DEMO-1")
    work_project(tmp_path, "boss_rpa", log=None, files=["note.md"])
    context, for_user = start(settings, tmp_path)
    assert for_user == "Dashboard: added cards for DEMO-1, boss_rpa (folders in work_jira)."
    assert notes.find_project(projects, "DEMO-1") and notes.find_project(projects, "boss_rpa")
    assert start(settings, tmp_path) == ("", "")                     # next time: nothing new to say


def test_session_start_can_archive_and_add_in_one_go(tmp_path):
    settings, projects = setup(tmp_path)
    gone = work_project(tmp_path, "DEMO-2")
    pn.create(projects, gone, "", "", NOW)
    os.rename(gone, tmp_path / "prod")
    work_project(tmp_path, "DEMO-3")
    _, for_user = start(settings, tmp_path)
    assert for_user == ("Dashboard: moved DEMO-2 to the Archive page (folder no longer in work_jira). "
                        "Added cards for DEMO-3 (folders in work_jira).")


def test_session_start_in_a_new_folder_asks_for_full_setup(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path, log=None, files=["ticket.md"])
    pn.create(projects, work, "Alarm update", "", NOW)           # + New project made the card and the folder
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
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path)
    (work / "requirements.md").write_text("- [ ] M1 — demo · Done when: test_demo passes\n", encoding="utf-8")
    pn.create(projects, work, "", "", NOW)
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
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path, log=None)
    pn.create(projects, work, "", "", NOW)
    stdin = io.StringIO(json.dumps({"cwd": str(work), "source": "startup"}))
    assert hooks.main(["session-start"], stdin, write_ini(tmp_path, settings), NOW) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "new project folder" in out["hookSpecificOutput"]["additionalContext"]
    assert "systemMessage" not in out


def test_main_session_start_tells_you_about_new_cards(tmp_path, capsys):
    settings, _ = setup(tmp_path)
    work_project(tmp_path, "DEMO-1")
    stdin = io.StringIO(json.dumps({"cwd": str(tmp_path), "source": "startup"}))
    assert hooks.main(["session-start"], stdin, write_ini(tmp_path, settings), NOW) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"systemMessage": "Dashboard: added cards for DEMO-1 (folders in work_jira)."}


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


# ---------- milestone guard: one milestone per session ----------

SESSION = "demo-session-1"
REQS = """## Milestones
- [ ] M<n> — <what it delivers> · Done when: <proof>
- [x] M1 — read the file · Done when: test_read passes
- [ ] M2 — parse the alarm file · Done when: test_parse passes
- [ ] M3 — email the report · Done when: user check — report arrives
"""


def ticket(tmp_path, reqs=REQS, log=LOG):
    """A set-up work_jira ticket with requirements.md (M1 ticked, M2 next) and a card."""
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path, log=log)
    if reqs is not None:
        (work / "requirements.md").write_text(reqs, encoding="utf-8")
    pn.create(projects, work, "", "", NOW)
    return settings, work


def begin(settings, work, source="startup", session=SESSION):
    return hooks.session_start({"cwd": str(work), "source": source, "session_id": session}, settings, NOW)


def tick(work, milestone="M2"):
    reqs = work / "requirements.md"
    reqs.write_text(reqs.read_text(encoding="utf-8").replace(f"- [ ] {milestone} ", f"- [x] {milestone} "),
                    encoding="utf-8")
    return reqs


def edited(path, session=SESSION):
    return hooks.after_edit({"session_id": session, "cwd": str(path.parent),
                             "tool_name": "Edit", "tool_input": {"file_path": str(path)}}, NOW)


def notepad(work, session=SESSION):
    return work / ".claude" / f"milestone-{session}.json"


def days_old(path, days):
    """Make a file look this many days older than NOW (the hooks' clock in these tests, not the real one)."""
    t = NOW.timestamp() - days * 24 * 3600
    os.utime(path, (t, t))


def test_session_start_writes_a_notepad_of_what_is_ticked_now(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    assert json.loads(notepad(work).read_text(encoding="utf-8"))["ticked"] == ["M1"]


def test_session_start_after_compact_or_resume_keeps_the_notepad(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    tick(work)
    for source in ("compact", "resume"):
        begin(settings, work, source)
        assert json.loads(notepad(work).read_text(encoding="utf-8"))["ticked"] == ["M1"]
    begin(settings, work, "clear")                       # /clear = a fresh start
    assert json.loads(notepad(work).read_text(encoding="utf-8"))["ticked"] == ["M1", "M2"]


def test_session_start_deletes_notepads_older_than_two_days(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work, session="old")
    begin(settings, work, session="yesterday")
    days_old(notepad(work, "old"), 3)
    days_old(notepad(work, "yesterday"), 1)
    begin(settings, work)
    assert not notepad(work, "old").exists() and notepad(work, "yesterday").exists() and notepad(work).exists()


def test_session_start_without_a_session_id_or_outside_a_ticket_writes_no_notepad(tmp_path):
    settings, work = ticket(tmp_path)
    hooks.session_start({"cwd": str(work), "source": "startup"}, settings, NOW)
    begin(settings, tmp_path)
    assert not (work / ".claude").exists() and not (tmp_path / ".claude").exists()


def test_session_start_in_a_ticket_without_real_milestones_asks_about_clear_requirements(tmp_path):
    settings, work = ticket(tmp_path, reqs="## Milestones\n- [ ] M<n> — <what> · Done when: <proof>\n")
    context, _ = begin(settings, work)
    assert "no milestones" in context and "ask the user" in context and "clear-requirements" in context
    (tmp_path / "b").mkdir()
    settings, work = ticket(tmp_path / "b", reqs=None)
    assert "clear-requirements" in begin(settings, work)[0]


def test_session_start_in_a_paused_ticket_without_milestones_says_nothing(tmp_path):
    settings, work = ticket(tmp_path, reqs="none yet — waiting for approval\n",
                            log=LOG.replace("M2 — parse the alarm file", "PENDING (user, 2026-10-22): waiting."))
    assert begin(settings, work) == ("", "")


def test_session_start_in_a_new_folder_says_setup_only_then_a_new_session(tmp_path):
    settings, projects = setup(tmp_path)
    work = work_project(tmp_path, log=None, files=["ticket.md"])
    context, _ = begin(settings, work)
    assert "_templates" in context and "ticket.md" in context
    assert "new session" in context and "Only set up" in context


def test_editing_another_file_says_nothing(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    assert edited(work / "tracking_log.md") == ""
    assert edited(work / "src" / "requirements.md") == ""       # not the ticket's own requirements.md


def test_ticking_a_milestone_gives_claude_the_checklist_once(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    message = edited(tick(work))
    assert "M2 ticked" in message and "/code-review low" in message
    assert "## Last update" in message and "2026-10-23 — M2 ticked" in message
    assert "Phase" in message and "STOP" in message and "do not start the next one" in message
    assert edited(work / "requirements.md") == ""              # told once, not on every later edit


def test_an_edit_without_a_new_tick_says_nothing(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    assert edited(work / "requirements.md") == ""               # M1 was ticked before the session


def test_no_notepad_means_no_milestone_checks(tmp_path):
    settings, work = ticket(tmp_path)
    tick(work)
    assert edited(work / "requirements.md") == ""
    assert hooks.prompt({"session_id": SESSION, "cwd": str(work)}) == hooks.ONE_STEP
    assert stop(settings, work) == (0, "")


def test_every_prompt_gets_the_one_step_reminder_anywhere():
    assert hooks.prompt({}) == hooks.ONE_STEP
    assert "ONE step" in hooks.ONE_STEP and "wait" in hooks.ONE_STEP


def test_after_a_tick_every_prompt_also_says_start_a_new_session(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    assert hooks.prompt({"session_id": SESSION, "cwd": str(work / "tests")}) == hooks.ONE_STEP
    tick(work)
    said = hooks.prompt({"session_id": SESSION, "cwd": str(work / "tests")})
    assert said.startswith(hooks.ONE_STEP) and "M2" in said and "new session" in said


def test_stop_after_a_tick_asks_once_for_the_tracking_log_update(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    tick(work)
    code, message = stop(settings, work)
    assert code == 2 and "2026-10-23 — M2 ticked" in message
    assert "## Now working on still names M2" in message and "M3" in message
    assert stop(settings, work, active=True) == (0, "")


def test_stop_is_quiet_once_the_tracking_log_is_updated(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    tick(work)
    (work / "tracking_log.md").write_text(
        LOG.replace("M2 — parse the alarm file\nand write its tests.", "M3 — email the report")
           .replace("2026-10-22 — M1 ticked, 4 tests green.", "2026-10-23 — M2 ticked, test_parse passes."),
        encoding="utf-8")
    assert stop(settings, work) == (0, "")


def test_stop_names_only_what_is_still_missing(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    tick(work)
    (work / "tracking_log.md").write_text(LOG.replace("2026-10-22 — M1", "2026-10-23 — M2"), encoding="utf-8")
    code, message = stop(settings, work)
    assert code == 2 and "Now working on still names M2" in message and "## Last update" not in message


def test_session_end_deletes_this_sessions_notepad_only(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    begin(settings, work, session="other")
    hooks.session_end({"session_id": SESSION, "cwd": str(work / "tests"), "reason": "prompt_input_exit"})
    assert not notepad(work).exists() and notepad(work, "other").exists()
    hooks.session_end({"session_id": "never-started", "cwd": str(work)})       # nothing to delete: no error


def test_a_session_id_cannot_point_outside_the_claude_folder(tmp_path):
    assert hooks.notepad_file(tmp_path, "../../evil") is None
    assert hooks.notepad_file(tmp_path, "") is None


def test_main_prompt_prints_context_json_even_without_settings(tmp_path, capsys):
    stdin = io.StringIO(json.dumps({"session_id": SESSION, "cwd": str(tmp_path)}))
    assert hooks.main(["prompt"], stdin, tmp_path / "missing.ini", NOW) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"] == {"hookEventName": "UserPromptSubmit", "additionalContext": hooks.ONE_STEP}
    assert hooks.main(["prompt"], io.StringIO("not json"), tmp_path / "missing.ini", NOW) == 0


def test_main_after_edit_prints_context_json_only_after_a_tick(tmp_path, capsys):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    event = {"session_id": SESSION, "cwd": str(work), "tool_name": "Edit",
             "tool_input": {"file_path": str(work / "requirements.md")}}
    assert hooks.main(["after-edit"], io.StringIO(json.dumps(event)), tmp_path / "missing.ini", NOW) == 0
    assert capsys.readouterr().out == ""
    tick(work)
    assert hooks.main(["after-edit"], io.StringIO(json.dumps(event)), tmp_path / "missing.ini", NOW) == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse" and "M2 ticked" in out["additionalContext"]


def test_main_session_end_exits_0(tmp_path):
    stdin = io.StringIO(json.dumps({"session_id": SESSION, "cwd": str(tmp_path)}))
    assert hooks.main(["session-end"], stdin, tmp_path / "missing.ini", NOW) == 0


def test_a_session_that_writes_requirements_md_has_no_milestone_checks(tmp_path):
    settings, work = ticket(tmp_path, reqs=None)
    begin(settings, work)
    assert not notepad(work).exists()
    (work / "requirements.md").write_text(REQS.replace("- [ ] M2", "- [x] M2"), encoding="utf-8")
    assert edited(work / "requirements.md") == ""


def test_now_working_on_counts_only_when_it_starts_with_the_ticked_milestone(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    tick(work)
    (work / "tracking_log.md").write_text(
        LOG.replace("M2 — parse the alarm file\nand write its tests.", "M3 — extend the M2 parser")
           .replace("2026-10-22 — M1 ticked", "2026-10-23 — M2 ticked"), encoding="utf-8")
    assert stop(settings, work) == (0, "")


def test_todays_line_must_name_the_ticked_milestone(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    tick(work)
    (work / "tracking_log.md").write_text(
        LOG.replace("M2 — parse the alarm file", "M3 — email the report")
           .replace("2026-10-22 — M1 ticked, 4 tests green.", "2026-10-23 — started M2 this morning, then M3 prep."),
        encoding="utf-8")
    code, message = stop(settings, work)
    assert code == 2 and "2026-10-23 — M2 ticked" in message


def test_stop_asks_about_each_milestone_once_per_session(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    tick(work)
    assert stop(settings, work)[0] == 2
    assert stop(settings, work) == (0, "")              # a later reply, log still not updated: not asked again
    tick(work, "M3")
    code, message = stop(settings, work)
    assert code == 2 and "M3" in message and "M2" not in message.split(":")[0]


def test_a_locked_old_notepad_does_not_stop_this_sessions_notepad(tmp_path):
    settings, work = ticket(tmp_path)
    stuck = work / ".claude" / "milestone-stuck.json"
    stuck.mkdir(parents=True)                            # can't be deleted like a file (like a locked file)
    days_old(stuck, 3)
    begin(settings, work)
    assert notepad(work).exists()


def test_each_prompt_keeps_a_long_session_notepad_fresh(tmp_path):
    settings, work = ticket(tmp_path)
    begin(settings, work)
    days_old(notepad(work), 3)
    hooks.prompt({"session_id": SESSION, "cwd": str(work)})
    begin(settings, work, session="second-window")
    assert notepad(work).exists()


def test_a_milestone_hook_problem_says_what_to_do(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(hooks, "find_notepad", lambda *a: (_ for _ in ()).throw(OSError("locked")))
    stdin = io.StringIO(json.dumps({"session_id": SESSION, "cwd": str(tmp_path)}))
    assert hooks.main(["prompt"], stdin, tmp_path / "missing.ini", NOW) == 0
    out = capsys.readouterr()
    assert hooks.ONE_STEP in out.out and "close" in out.err and "milestone-" in out.err


# ---------- phase -> skills reminder at session start ----------

PAUSED = LOG.replace("M2 — parse the alarm file", "PENDING (user, 2026-10-22): waiting.")
TEMPLATE_PHASE = "- **Phase:** 1-Understand | 2-Plan | 3-Build | 4-Review | 5-Handover"


def phase_ticket(tmp_path, phase_line, reqs=REQS, log=LOG):
    """A set-up ticket whose CLAUDE.md has this Phase line (None = no CLAUDE.md at all)."""
    settings, work = ticket(tmp_path, reqs=reqs, log=log)
    if phase_line is not None:
        (work / "CLAUDE.md").write_text(f"# DEMO-42\n\n- **Jira:** DEMO-42\n{phase_line}\n", encoding="utf-8")
    return settings, work


@pytest.mark.parametrize("line, skills", [
    ("- **Phase:** 2-Plan", ["writing-plans"]),
    ("- **Phase:** 3-Build", ["test-driven-development", "verification-before-completion"]),
    ("- **Phase:** 4-Review", ["receiving-code-review", "verification-before-completion"]),
    ("Phase: 3 - build", ["test-driven-development"]),
    ("**Phase:** 2", ["writing-plans"]),
])
def test_session_start_names_the_skills_for_the_tickets_phase(tmp_path, line, skills):
    settings, work = phase_ticket(tmp_path, line)
    context, _ = begin(settings, work)
    assert all(s in context for s in skills) and "no milestones" not in context


@pytest.mark.parametrize("line", [
    "- **Phase:** 1-Understand",
    "- **Phase:** 5-Handover",
    "| `writing-plans` | 2-Plan | Milestone lines |",          # a skills table row is not the Phase line
    None,                                                     # no CLAUDE.md (folders with only tracking_log.md)
])
def test_session_start_says_nothing_for_phases_without_skills_or_no_phase_line(tmp_path, line):
    settings, work = phase_ticket(tmp_path, line)
    assert begin(settings, work) == ("", "")


@pytest.mark.parametrize("line", [TEMPLATE_PHASE, "- **Phase:** TBD"])
def test_session_start_with_the_phase_not_set_asks_claude_to_get_it_confirmed(tmp_path, line):
    settings, work = phase_ticket(tmp_path, line)
    context, _ = begin(settings, work)
    assert "Phase" in context and "ask the user to confirm" in context and "CLAUDE.md" in context


@pytest.mark.parametrize("line", ["- **Phase:** 3-Build", TEMPLATE_PHASE])
def test_session_start_in_a_paused_ticket_never_mentions_the_phase(tmp_path, line):
    settings, work = phase_ticket(tmp_path, line, log=PAUSED)
    assert begin(settings, work) == ("", "")


def test_session_start_asks_for_the_phase_before_the_missing_milestones(tmp_path):
    settings, work = phase_ticket(tmp_path, TEMPLATE_PHASE, reqs="## Milestones\n")
    context, _ = begin(settings, work)
    assert 0 <= context.index("ask the user to confirm") < context.index("no milestones")


def test_every_phase_skill_is_one_of_our_own_skills():
    own = Path(hooks.__file__).with_name("work_jira_skills")
    named = {s for _, skills in hooks.PHASE_SKILLS.values() for s in skills}
    assert named and all((own / s / "SKILL.md").is_file() for s in named)
