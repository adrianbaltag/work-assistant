"""The gate: the hook that runs before Claude writes a file (PreToolUse) and stops code that comes too early.

Rules (decided 2026-11-15), only inside ticket folders under work_jira:
    no creator's yes            -> notes only (any .md file, and .gitignore)
    yes, no approved plan       -> notes and PLAN.md
    approved plan, open milestone -> everything
    a milestone ticked in this session -> notes only
Anything unclear (a crash, a locked file, no settings) lets the write through: only a clear "no" stops it.

Folders are fake (tmp_path), hook input is fake JSON, all text is made up.
"""
import io
import json
from pathlib import PurePosixPath, PureWindowsPath

import pytest

import project_note as pn
import work_jira_hooks as hooks
from test_work_jira_hooks import NOW, SESSION, begin, setup, tick, write_ini
from test_project_note import LOG, work_project

WAITING = """# DEMO-42 — requirements

**Status:** WAITING FOR CREATOR (since 2026-11-14)

## Questions for the creator (Maria)
1. Is it right that only late orders count?
"""

CONFIRMED = """# DEMO-42 — requirements

**Status:** CONFIRMED BY CREATOR (2026-11-15)

## The creator's yes
> Yes, go ahead.
(Maria, Slack, 2026-11-15)
"""

MILESTONES = """
## Milestones
{approved}
- [x] M1 — read the file · Done when: test_read passes
- [ ] M2 — parse the alarm file · Done when: test_parse passes
- [ ] M3 — email the report · Done when: user check — report arrives
"""

DRAFT = CONFIRMED + MILESTONES.format(approved="")
PLANNED = CONFIRMED + MILESTONES.format(approved="Plan approved by Sam (2026-11-15)\n")
ALL_TICKED = PLANNED.replace("- [ ]", "- [x]")
CLOSED = ALL_TICKED + "\n## Closed\n> Works, thanks.\n(Maria, Slack, 2026-11-20)\n"
OLD = MILESTONES.format(approved="")                      # a ticket from before ticket-flow: no Status line
OLD_NO_MILESTONES = "# DEMO-42\n\nSend a report of the late orders every morning.\n"
# An old ticket whose own text has a line that starts with "Status:". It is a requirement, not our Status line.
OLD_STATUS_BULLET = "# DEMO-42\n\n- Status: only open alarms count\n- Status : closed ones are skipped\n" + OLD
YES_LINE = "\n**Status:** CONFIRMED BY CREATOR (2026-11-15)\n"


def ticket(tmp_path, reqs):
    """A ticket folder DEMO-42 under work_jira with this requirements.md (None = no such file)."""
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path, log=LOG)
    if reqs is not None:
        (work / "requirements.md").write_text(reqs, encoding="utf-8")
    return settings, work


def write(settings, path, session=SESSION, tool="Write"):
    """What the gate says when Claude is about to write this file: "" = go ahead, else the stop message."""
    return hooks.gate({"session_id": session, "tool_name": tool, "tool_input": {"file_path": str(path)}}, settings)


# ---------- which file belongs to which ticket (Windows and Mac paths) ----------

WORK_JIRA = r"C:\Users\demo\Desktop\work_jira"


def test_a_windows_path_inside_a_ticket_folder_is_found():
    found = hooks.ticket_file(WORK_JIRA, r"C:\Users\demo\Desktop\work_jira\ABC-12\report.py", PureWindowsPath)
    assert found == ("ABC-12", PureWindowsPath("report.py"))
    deeper = hooks.ticket_file(WORK_JIRA, r"C:\Users\demo\Desktop\work_jira\ABC-12\tests\test_report.py", PureWindowsPath)
    assert deeper == ("ABC-12", PureWindowsPath(r"tests\test_report.py"))


def test_on_windows_capitals_and_the_kind_of_slash_do_not_matter():
    typed_in_settings = "c:/users/DEMO/desktop/Work_Jira"
    found = hooks.ticket_file(typed_in_settings, r"C:\Users\demo\Desktop\work_jira\ABC-12\report.py", PureWindowsPath)
    assert found == ("ABC-12", PureWindowsPath("report.py"))


@pytest.mark.parametrize("path", [
    r"C:\Users\demo\Desktop\work_jira\CLAUDE.md",                 # in work_jira itself, in no ticket
    r"C:\Users\demo\Desktop\work_jira_old\ABC-12\report.py",      # a folder whose name only starts the same
    r"C:\Users\demo\Desktop\other\report.py",
    r"D:\Users\demo\Desktop\work_jira\ABC-12\report.py",          # another drive
    r"C:\Users\demo\Desktop\work_jira\_templates\CLAUDE.md",      # _ and . folders are not tickets
    r"C:\Users\demo\Desktop\work_jira\.claude\settings.json",
])
def test_a_windows_path_outside_every_ticket_folder_is_not_gated(path):
    assert hooks.ticket_file(WORK_JIRA, path, PureWindowsPath) is None


def test_a_mac_path_inside_a_ticket_folder_is_found():
    found = hooks.ticket_file("/Users/demo/Desktop/work_jira", "/Users/demo/Desktop/work_jira/ABC-12/src/report.py",
                              PurePosixPath)
    assert found == ("ABC-12", PurePosixPath("src/report.py"))
    assert hooks.ticket_file("/Users/demo/Desktop/work_jira", "/Users/demo/Desktop/notes/report.py", PurePosixPath) is None


def test_a_work_jira_folder_that_is_not_a_full_path_gates_nothing():
    assert hooks.ticket_file("work_jira", "work_jira/ABC-12/report.py", PurePosixPath) is None


# ---------- what is a note ----------

@pytest.mark.parametrize("name", ["requirements.md", "tracking_log.md", "ticket.md", "CLAUDE.md", "MY_DEFAULTS.md",
                                  "anything.MD", "docs/questions.md", ".gitignore"])
def test_any_md_file_and_gitignore_are_notes(name):
    assert hooks.is_note(PurePosixPath(name))


@pytest.mark.parametrize("name", ["report.py", "PLAN.md", "plan.md", "data.csv", "notes.md.py", "tests/test_report.py",
                                  "README.txt", "report.ipynb"])
def test_code_data_and_the_plan_are_not_notes(name):
    assert not hooks.is_note(PurePosixPath(name))


# ---------- where a ticket stands, read from its files ----------

@pytest.mark.parametrize("reqs, state", [
    (None, "new"),
    ("", "new"),
    ("<!-- nothing yet -->\n", "new"),
    (OLD_NO_MILESTONES, "old"),
    (OLD, "old"),
    (WAITING, "waiting"),
    (CONFIRMED, "plan"),
    (DRAFT, "plan"),                                        # milestones, but the engineer did not approve them yet
    (CONFIRMED + "\nPlan approved by Sam (2026-11-15)\n", "plan"),      # approved, but there is no milestone line
    (PLANNED, "build"),
    (ALL_TICKED, "done"),
    (CLOSED, "closed"),
    (CLOSED.replace("## Closed", "   ## Closed"), "closed"),            # review finding 2026-11-15: copied with the
    (CLOSED.replace("## Closed", "## Closed (2026-11-20)"), "closed"),  # skill's indent, or with a date after it
    (CLOSED.replace("## Closed", "## Closed: 2026-11-20"), "closed"),
    (ALL_TICKED + "\n## Closed questions\nNone.\n", "done"),            # another heading that only starts the same
    (ALL_TICKED + "\nWe said ## Closed comes later.\n", "done"),
    (PLANNED.replace("**Status:** CONFIRMED", "Status: confirmed"), "build"),      # typed by hand, a little differently
    (WAITING + "\nWe write CONFIRMED BY CREATOR here once Maria says yes.\n", "waiting"),   # prose is not the Status line
    (OLD_STATUS_BULLET, "old"),                             # a requirement that starts with "Status:" is not it either
    (OLD_STATUS_BULLET + YES_LINE, "plan"),                 # the yes counts wherever it is added, also below that bullet
    (OLD_STATUS_BULLET + YES_LINE + "Plan approved by Sam (2026-11-15)\n", "build"),
    ("**Status:** draft, not sent yet\n", "old"),            # only the two Status lines the skill writes count
    (WAITING + YES_LINE, "plan"),                           # an old waiting line left in: the yes wins
    ("<!-- **Status:** CONFIRMED BY CREATOR -->\n" + WAITING, "waiting"),          # a commented-out line does not count
])
def test_the_state_of_a_ticket_comes_from_its_requirements_file(tmp_path, reqs, state):
    _, work = ticket(tmp_path, reqs)
    assert hooks.ticket_state(work) == state


# ---------- the gate itself ----------

@pytest.mark.parametrize("reqs", [None, OLD_NO_MILESTONES, OLD, WAITING])
def test_before_the_creators_yes_only_notes_can_be_written(tmp_path, reqs):
    settings, work = ticket(tmp_path, reqs)
    for note in ("requirements.md", "tracking_log.md", "ticket.md", "CLAUDE.md", "questions.md", ".gitignore"):
        assert write(settings, work / note) == ""
    for other in ("report.py", "PLAN.md", "tests/test_report.py", "data.csv"):
        message = write(settings, work / other)
        assert "Not written" in message and "ticket-flow:clear-ticket" in message
        assert "only notes" in message


def test_the_stop_message_names_the_file_and_the_ticket(tmp_path):
    settings, work = ticket(tmp_path, WAITING)
    message = write(settings, work / "src" / "report.py")
    assert "report.py" in message and "DEMO-42" in message


def test_after_the_yes_the_plan_can_be_written_but_no_code(tmp_path):
    for i, reqs in enumerate((CONFIRMED, DRAFT)):
        (tmp_path / str(i)).mkdir()
        settings, work = ticket(tmp_path / str(i), reqs)
        assert write(settings, work / "PLAN.md") == ""
        assert write(settings, work / "requirements.md") == ""
        message = write(settings, work / "report.py")
        assert "Not written" in message and "ticket-flow:plan-milestones" in message
        assert "PLAN.md" in message                              # says what can be written meanwhile


def test_with_an_approved_plan_and_an_open_milestone_everything_can_be_written(tmp_path):
    settings, work = ticket(tmp_path, PLANNED)
    begin(settings, work)
    for name in ("report.py", "tests/test_report.py", "PLAN.md", "requirements.md", "data.csv", ".claude/review-files.txt"):
        assert write(settings, work / name) == ""


def test_after_a_tick_in_this_session_only_notes_can_be_written(tmp_path):
    settings, work = ticket(tmp_path, PLANNED)
    begin(settings, work)
    tick(work)
    message = write(settings, work / "report.py")
    assert "Not written" in message and "M2" in message and "new session" in message
    assert "untick" in message                                   # the way out when the tick was a mistake
    assert write(settings, work / "tracking_log.md") == ""       # the closing steps are notes
    assert write(settings, work / "requirements.md") == ""
    plan = write(settings, work / "PLAN.md")                     # review finding 2026-11-15: the plan slipped through
    assert "Not written" in plan and "M2" in plan and "not PLAN.md" in plan


def test_unticking_the_box_opens_the_gate_again(tmp_path):
    settings, work = ticket(tmp_path, PLANNED)
    begin(settings, work)
    reqs = tick(work)
    assert write(settings, work / "report.py") != ""
    reqs.write_text(PLANNED, encoding="utf-8")                   # the tick was a mistake: M2 is open again
    assert write(settings, work / "report.py") == ""


def test_a_tick_from_another_session_does_not_lock_this_one(tmp_path):
    settings, work = ticket(tmp_path, PLANNED)
    begin(settings, work, session="yesterday")
    tick(work)
    begin(settings, work)                                        # a new session starts with M2 already ticked
    assert write(settings, work / "report.py") == ""


def test_without_a_notepad_a_tick_locks_nothing(tmp_path):
    settings, work = ticket(tmp_path, PLANNED)
    tick(work)                                                   # no session start here: nothing to compare with
    assert write(settings, work / "report.py") == ""


def test_when_every_milestone_is_ticked_code_waits_for_a_new_milestone(tmp_path):
    settings, work = ticket(tmp_path, ALL_TICKED)
    begin(settings, work)
    message = write(settings, work / "report.py")
    assert "Not written" in message and "ticket-flow:build-milestone" in message and "ticket-flow:plan-milestones" in message
    assert write(settings, work / "tracking_log.md") == "" and write(settings, work / "PLAN.md") == ""


def test_a_closed_ticket_takes_notes_only(tmp_path):
    settings, work = ticket(tmp_path, CLOSED)
    message = write(settings, work / "report.py")
    assert "closed" in message and "ticket-flow:clear-ticket" in message
    assert "new ticket" in message and "own folder" in message   # decided 2026-11-15: a closed folder stays closed
    assert write(settings, work / "tracking_log.md") == ""
    plan = write(settings, work / "PLAN.md")                     # no new plan in a closed folder either
    assert "Not written" in plan and "closed" in plan and "not PLAN.md" in plan


def test_a_new_plan_does_not_open_a_closed_ticket_again(tmp_path):
    """A new wish is a new ticket in its own folder. Milestones added to a closed one change nothing."""
    more = CLOSED.replace("## Closed", "- [ ] M4 — one more column · Done when: test_column passes\n\n## Closed")
    settings, work = ticket(tmp_path, more)
    assert hooks.ticket_state(work) == "closed"
    assert "own folder" in write(settings, work / "report.py")


def test_an_old_ticket_gets_one_stop_that_asks_both_questions_together(tmp_path):
    settings, work = ticket(tmp_path, OLD)
    message = write(settings, work / "report.py")
    assert "ONE message" in message
    assert "Did the creator confirm" in message and "Do you approve" in message
    assert "ticket-flow:clear-ticket" in message and "ticket-flow:plan-milestones" in message


def test_an_old_ticket_without_milestones_is_only_asked_about_the_creator(tmp_path):
    settings, work = ticket(tmp_path, OLD_NO_MILESTONES)
    message = write(settings, work / "report.py")
    assert "ticket-flow:clear-ticket" in message and "Do you approve" not in message


def test_a_file_in_a_ticket_folder_that_does_not_exist_yet_is_gated_too(tmp_path):
    settings, _ = setup(tmp_path)
    assert "ticket-flow:clear-ticket" in write(settings, tmp_path / "work_jira" / "DEMO-99" / "report.py")
    assert write(settings, tmp_path / "work_jira" / "DEMO-99" / "ticket.md") == ""


def test_the_gate_looks_at_where_the_file_is_not_at_where_claude_is(tmp_path):
    settings, work = ticket(tmp_path, WAITING)
    event = {"session_id": SESSION, "cwd": str(tmp_path), "tool_name": "Edit",
             "tool_input": {"file_path": str(work / "report.py")}}
    assert "Not written" in hooks.gate(event, settings)
    roundabout = tmp_path / "work_jira" / "DEMO-42" / "src" / ".." / "report.py"
    assert "Not written" in write(settings, roundabout)


def test_a_notebook_is_gated_like_any_other_code_file(tmp_path):
    settings, work = ticket(tmp_path, WAITING)
    event = {"session_id": SESSION, "tool_name": "NotebookEdit", "tool_input": {"notebook_path": str(work / "look.ipynb")}}
    assert "Not written" in hooks.gate(event, settings)


def test_files_outside_the_ticket_folders_are_never_stopped(tmp_path):
    settings, work = ticket(tmp_path, WAITING)
    assert write(settings, tmp_path / "elsewhere" / "report.py") == ""
    assert write(settings, tmp_path / "work_jira" / "CLAUDE.md") == ""
    assert write(settings, tmp_path / "work_jira" / "_templates" / "report.py") == ""
    assert write({**settings, "work_jira_folder": ""}, work / "report.py") == ""      # sync with work_jira is off
    assert hooks.gate({"tool_name": "Write", "tool_input": {}}, settings) == ""       # no path: nothing to judge
    assert hooks.gate({}, settings) == ""


# ---------- main: exit 2 stops the write, any problem lets it through ----------

def run_gate(tmp_path, settings, path, capsys):
    event = {"session_id": SESSION, "tool_name": "Write", "tool_input": {"file_path": str(path)}}
    code = hooks.main(["gate"], io.StringIO(json.dumps(event)), write_ini(tmp_path, settings), NOW)
    return code, capsys.readouterr()


def test_main_gate_stops_a_write_with_exit_2_and_the_message_for_claude(tmp_path, capsys):
    settings, work = ticket(tmp_path, WAITING)
    code, out = run_gate(tmp_path, settings, work / "report.py", capsys)
    assert code == 2 and "Not written" in out.err and "ticket-flow:clear-ticket" in out.err
    assert out.out == ""


def test_main_gate_lets_a_note_through_and_says_nothing(tmp_path, capsys):
    settings, work = ticket(tmp_path, WAITING)
    code, out = run_gate(tmp_path, settings, work / "requirements.md", capsys)
    assert (code, out.out, out.err) == (0, "", "")


def test_a_file_that_cannot_be_read_never_stops_claude(tmp_path, capsys, monkeypatch):
    settings, work = ticket(tmp_path, WAITING)

    def locked(folder):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(pn, "requirements_text", locked)
    code, out = run_gate(tmp_path, settings, work / "report.py", capsys)
    assert code == 1 and "Claude can carry on" in out.err       # exit 1 = shown, the write goes ahead


def test_missing_settings_or_bad_hook_input_never_stop_claude(tmp_path, capsys):
    _, work = ticket(tmp_path, WAITING)
    event = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(work / "report.py")}})
    assert hooks.main(["gate"], io.StringIO(event), tmp_path / "missing.ini", NOW) == 1
    settings = {"projects_folder": str(tmp_path / "projects"), "work_jira_folder": str(tmp_path / "work_jira")}
    assert hooks.main(["gate"], io.StringIO("not json"), write_ini(tmp_path, settings), NOW) == 0
    assert hooks.main(["gate"], io.StringIO('{"tool_input": "odd"}'), write_ini(tmp_path, settings), NOW) != 2


def test_the_gate_works_without_a_projects_folder(tmp_path, capsys):
    """The gate reads the ticket folder only: a wrong projects_folder= must not switch it off or break it."""
    settings, work = ticket(tmp_path, WAITING)
    code, _ = run_gate(tmp_path, {**settings, "projects_folder": ""}, work / "report.py", capsys)
    assert code == 2


# ---------- session start names the next step, from the ticket's files ----------

@pytest.mark.parametrize("reqs, skill, words", [
    (None, "ticket-flow:clear-ticket", "no creator's yes"),
    (WAITING, "ticket-flow:clear-ticket", "waits for the creator"),
    (CONFIRMED, "ticket-flow:plan-milestones", "no approved plan"),
    (DRAFT, "ticket-flow:plan-milestones", "no approved plan"),
    (PLANNED, "ticket-flow:build-milestone", "M2"),              # M1 is ticked: M2 is the first open one
    (ALL_TICKED, "ticket-flow:build-milestone", "Closing the ticket"),
    (CLOSED, "ticket-flow:clear-ticket", "own folder"),         # a new wish is a new ticket, not this folder again
])
def test_session_start_names_the_next_skill_for_where_the_ticket_stands(tmp_path, reqs, skill, words):
    settings, work = ticket(tmp_path, reqs)
    (work / ".git").mkdir()
    context, _ = begin(settings, work)
    assert skill in context and words in context
    assert "Not written" not in context                          # nothing was stopped: this is only the next step
    for old in ("clear-requirements", "grill-me", "writing-plans", "_templates", "/code-review", "/close-out"):
        assert old not in context


def test_session_start_in_an_old_ticket_asks_both_questions_in_one_message(tmp_path):
    settings, work = ticket(tmp_path, OLD)
    (work / ".git").mkdir()
    context, _ = begin(settings, work)
    assert "ONE message" in context and "Did the creator confirm" in context and "Do you approve" in context


def test_session_start_in_a_ticket_that_waits_says_nothing(tmp_path):
    """PENDING = the ticket waits for someone. Nothing to push: the engineer comes back with the reply."""
    settings, _ = setup(tmp_path)
    waiting_log = LOG.replace("M2 — parse the alarm file",
                              "PENDING (creator, 2026-11-14): waiting for Maria to answer 3 questions.")
    work = work_project(tmp_path, log=waiting_log)
    (work / "requirements.md").write_text(WAITING, encoding="utf-8")
    assert begin(settings, work)[0] == ""                        # [1] is the "card added" note for the user


def test_a_requirement_that_starts_with_status_never_keeps_the_gate_shut(tmp_path):
    """Review finding 2026-11-15: such a line was read as the Status line, and the creator's yes below it was not seen."""
    settings, work = ticket(tmp_path, OLD_STATUS_BULLET)
    message = write(settings, work / "report.py")
    assert "was started before ticket-flow" in message and "waits for the creator" not in message
    (work / "requirements.md").write_text(OLD_STATUS_BULLET + YES_LINE + "Plan approved by Sam (2026-11-15)\n",
                                          encoding="utf-8")
    assert write(settings, work / "report.py") == ""             # both answers written down: the gate is open
