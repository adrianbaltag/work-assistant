"""G4: reopen a closed ticket, and "this ticket is done" closes a ticket at any stage.

Decided 2026-11-21 (all A): the newest of `## Closed` / `## Reopened` decides; closed wins at every stage
(also before the creator's yes); after a reopen Claude proposes the fix milestone in the same reply, and it is
built in a new session. Made-up IDs only.
"""
import json
from pathlib import Path

import pytest

import work_jira_hooks as hooks
from test_completed import card, client, folders, ticket as work_folder, rows   # noqa: F401 (fixtures)
from test_ticket_flow import PLUGIN, front_matter, section, skill_text, table_row
from test_ticket_gate import ALL_TICKED, CLOSED, CONFIRMED, OLD, PLANNED, WAITING, ticket, write
from test_work_jira_hooks import begin

REOPENED = CLOSED + "\n## Reopened (2026-11-22): the report skips Sundays\n"
FIX = "- [ ] M4 — Sundays counted · Done when: test_sundays passes\n"
REOPENED_WITH_FIX = REOPENED + FIX                      # the fix milestone goes under the ## Reopened heading
FIX_TICKED = REOPENED + FIX.replace("- [ ]", "- [x]")
CLOSED_AGAIN = REOPENED + "\n## Closed\nClosed by Sam (2026-11-25): fixed.\n"
REPO = Path(hooks.__file__).parent


# ---------- where a ticket stands: the newest of ## Closed / ## Reopened decides ----------

@pytest.mark.parametrize("reqs, state", [
    (REOPENED, "reopened"),                                 # every milestone ticked: the fix needs a new milestone
    (FIX_TICKED, "done"),                                   # the fix is built: time to close again
    (REOPENED_WITH_FIX, "build"),                           # the fix milestone is the open one
    (CLOSED_AGAIN, "closed"),                               # closed again: a second ## Closed under the reopen
    (CLOSED.replace("## Closed", "## Reopened: too early\n\n## Closed"), "closed"),     # order in the file decides
    (CLOSED + "\n   ## Reopened\n", "reopened"),            # copied with an indent
    (CLOSED + "\n## Reopened: 2026-11-22\n", "reopened"),
    (CLOSED + "\n## Reopened questions\nNone.\n", "closed"),     # another heading that only starts the same
    (CLOSED + "\n<!-- ## Reopened -->\n", "closed"),        # a commented-out line does not count
    # closed wins at every stage (a dropped ticket can end anywhere)
    (WAITING + "\n## Closed\nClosed by Sam (2026-11-21): dropped.\n", "closed"),
    (CONFIRMED + "\n## Closed\nClosed by Sam (2026-11-21): dropped.\n", "closed"),
    (PLANNED + "\n## Closed\nClosed by Sam (2026-11-21): dropped.\n", "closed"),
    (OLD + "\n## Closed\nClosed by Sam (2026-11-21): dropped.\n", "closed"),
    # reopened before the creator's yes: back where it stood
    (WAITING + "\n## Closed\nDropped.\n\n## Reopened (2026-11-22): back on\n", "waiting"),
    (PLANNED + "\n## Closed\nDropped.\n\n## Reopened (2026-11-22): back on\n", "build"),
])
def test_the_newest_of_closed_and_reopened_decides(tmp_path, reqs, state):
    _, work = ticket(tmp_path, reqs)
    assert hooks.ticket_state(work) == state


@pytest.mark.parametrize("reqs, closed", [
    (CLOSED, True), (REOPENED, False), (CLOSED_AGAIN, True), (PLANNED, False), (ALL_TICKED, False),
    (WAITING + "\n## Closed\nDropped.\n", True), ("", False),
])
def test_is_closed_is_the_one_answer_for_the_hooks_and_the_dashboard(reqs, closed):
    assert hooks.is_closed(reqs) is closed


# ---------- the gate after a reopen ----------

def test_a_reopened_ticket_takes_the_fix_milestone_first_then_code(tmp_path):
    settings, work = ticket(tmp_path, REOPENED)
    begin(settings, work)
    stopped = write(settings, work / "report.py")
    assert "Not written" in stopped and "ticket-flow:plan-milestones" in stopped     # add the fix milestone first
    assert "Closing the ticket" not in stopped                    # review 2026-11-21: nothing was fixed yet
    context, _ = begin(settings, work)
    assert "Reopening the ticket" in context and "Closing the ticket" not in context
    assert write(settings, work / "PLAN.md") == "" and write(settings, work / "requirements.md") == ""

    (work / "requirements.md").write_text(REOPENED_WITH_FIX, encoding="utf-8")
    assert write(settings, work / "report.py") == ""                                  # open milestone: code


def test_a_closed_ticket_says_how_to_reopen_it(tmp_path):
    settings, work = ticket(tmp_path, CLOSED)
    stopped = write(settings, work / "report.py")
    assert "reopen: <what broke>" in stopped and "Reopening the ticket" in stopped
    assert "new ticket" in stopped and "own folder" in stopped           # a new wish still gets its own folder
    assert "stays closed" not in stopped

    (work / ".git").mkdir()
    context, _ = begin(settings, work)
    assert "reopen: <what broke>" in context and "ticket-flow:plan-milestones" in context
    assert "stays closed" not in context


def test_a_dashboard_note_on_a_closed_ticket_mentions_the_reopen():
    note = hooks.HOW["closed"]
    assert "reopen: <what broke>" in note and "new ticket" in note


# ---------- the dashboard: a reopened ticket is in progress again ----------

def test_a_reopened_ticket_is_grey_again_and_green_once_closed_again(folders, client):    # noqa: F811
    projects, work = folders
    card(projects, "ABC-1", linked_to=work_folder(work, "ABC-1", REOPENED))
    card(projects, "ABC-2", linked_to=work_folder(work, "ABC-2", CLOSED_AGAIN))

    got = {name: r["ready"] for name, r in rows(client).items()}

    assert got == {"ABC-1": "", "ABC-2": "closed"}


def test_complete_on_a_reopened_ticket_is_refused_with_plain_words(folders, client):     # noqa: F811
    projects, work = folders
    card(projects, "ABC-1", linked_to=work_folder(work, "ABC-1", REOPENED))

    answer = client.post("/api/projects/ABC-1/complete", json={})

    assert answer.status_code == 400
    assert "not closed" in answer.json["error"] and "no ## Closed" not in answer.json["error"]


# ---------- the skills ----------

def test_build_milestone_sends_a_reopened_ticket_with_no_fix_milestone_to_plan_milestones():
    """Review 2026-11-21: else "take the next row" reaches "Every milestone is ticked" and closes it unfixed."""
    row = table_row(section(skill_text("build-milestone"), "Step 0"), "`requirements.md` has a `## Closed` section")
    assert "every milestone is ticked and no milestone line under it" in row
    # review round 2, 2026-11-21: a ticket closed early (M2 still open) goes back to its own stage
    assert "else take the next row that fits" in row


def test_plan_milestones_sends_a_reopened_ticket_with_no_fix_milestone_to_the_fix_step():
    """Review round 2, 2026-11-21: else "the plan is done, go build" and build-milestone sends it back here."""
    step_0 = section(skill_text("plan-milestones"), "Step 0")
    row = table_row(step_0, "Milestone lines, a `Plan approved by` line, every milestone ticked")
    assert "## Reopened" in row and "no milestone line under it" in row
    assert '"Reopening the ticket"' in row
    assert step_0.index(row) < step_0.index("| Milestone lines and a `Plan approved by` line |")   # first row that fits
    assert "already written, logged and committed" in row


def test_the_reopen_is_logged_and_committed_before_the_fix_milestone_and_every_pointer_names_that_step():
    """Review rounds 3 and 4, 2026-11-21: with the log and commit AFTER the milestone question, a later session
    came in at the milestone step and either wrote "ticket reopened" twice or never. Now the reopen is logged and
    committed first, and the fix-milestone step only adds the milestone ("Plan changed")."""
    import re
    reopening = section(skill_text("plan-milestones"), "Reopening the ticket")
    fix_step = re.search(r"^(\d+)\. \*\*The fix milestone\.\*\*", reopening, re.M)
    step = f"step {fix_step.group(1)}"
    assert reopening.index("ticket reopened: <what broke>") < fix_step.start()
    assert reopening.index('git commit -m "Ticket reopened"') < fix_step.start()
    milestone_part = " ".join(reopening[fix_step.start():].split())
    assert '`git commit -m "Plan changed"`' in milestone_part and "commit of step" not in milestone_part
    assert "ticket reopened" not in milestone_part.split("Tell the engineer")[0]

    assert step in hooks.STEPS["reopened"]
    assert step in table_row(section(skill_text("build-milestone"), "Step 0"), "`requirements.md` has a `## Closed` section")
    assert step in table_row(section(skill_text("plan-milestones"), "Step 0"),
                             "Milestone lines, a `Plan approved by` line, every milestone ticked")


def test_build_milestone_closes_the_ticket_at_any_stage_when_the_engineer_says_so():
    step_0 = section(skill_text("build-milestone"), "Step 0")
    done_row = table_row(step_0, "The engineer says the ticket is done")
    assert "any stage" in done_row and "Closing the ticket" in done_row
    # "take the first row that fits": the engineer's word and a closed ticket come before every stage row
    assert step_0.index(done_row) < step_0.index("`## Closed`") < step_0.index("Status is not `CONFIRMED BY CREATOR`")

    closing = section(skill_text("build-milestone"), "Closing the ticket")
    assert not closing.split("\n", 2)[2].strip().startswith("Every milestone is ticked")
    assert "at any stage" in closing


@pytest.mark.parametrize("name", ["clear-ticket", "plan-milestones"])
def test_the_other_skills_hand_the_engineers_close_to_build_milestone(name):
    step_0 = section(skill_text(name), "Step 0")
    row = table_row(step_0, "The engineer says the ticket is done")
    assert "ticket-flow:build-milestone" in row and "Closing the ticket" in row


@pytest.mark.parametrize("name", ["clear-ticket", "plan-milestones", "build-milestone"])
def test_a_closed_ticket_in_any_skill_points_to_the_reopen(name):
    row = table_row(section(skill_text(name), "Step 0"), "`requirements.md` has a `## Closed` section")
    assert "stays closed" not in row
    assert "reopen: <what broke>" in row and "Reopening the ticket" in row and "own folder" in row


def test_plan_milestones_says_how_to_reopen():
    """In plan-milestones: a reopen adds the fix milestone (and build-milestone is at its 500-line limit)."""
    text = skill_text("plan-milestones")
    fields, _ = front_matter(text)
    assert "reopen" in fields["description"]
    assert "the ticket is done" in front_matter(skill_text("build-milestone"))[0]["description"]

    reopening = " ".join(section(text, "Reopening the ticket").split())
    assert "a fault or a small change" in reopening and "new wish" in reopening       # Claude asks first
    assert "## Reopened (<date>): <what broke>" in reopening                          # the very heading the hook reads
    assert "the engineer's own words" in reopening
    assert ".work-assistant-completed" in reopening and "Restore" in reopening        # the folder must come back first
    assert "PROD_SCRIPTS" not in reopening        # review 2026-11-21: only the default name; the tag file finds it
    assert "under the `## Reopened` heading" in reopening        # where the hooks look for the fix milestone
    assert '"Changing the plan later" above' in reopening                                   # the fix = a new milestone
    assert "YYYY-MM-DD — ticket reopened: <what broke>" in reopening
    assert 'git commit -m "Ticket reopened"' in reopening
    assert "new session" in reopening                                                  # built in a new session


# ---------- the words for people ----------

def rule_block():
    text = (REPO / "work_jira_rules.md").read_text(encoding="utf-8")
    return " ".join(text[text.index("```markdown"):text.rindex("```")].split())


def test_the_rule_block_says_how_to_close_and_reopen():
    rules = rule_block()
    assert "reopen: <what broke>" in rules and "## Reopened" in rules
    assert "this ticket is done" in rules and "at any stage" in rules
    assert "stays closed" not in rules


@pytest.mark.parametrize("readme", ["README.md", "ticket-flow/README.md"])
def test_no_readme_says_a_closed_ticket_stays_closed(readme):
    text = " ".join((REPO / readme).read_text(encoding="utf-8").split())
    assert "stays closed" not in text and "A closed ticket stays closed" not in text
    assert "reopen: <what broke>" in text


def test_the_plugin_version_is_bumped_for_g4():
    """The Mac's copy of the plugin is keyed by version: every plugin change needs a new one."""
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    assert tuple(int(part) for part in version.split(".")) >= (0, 1, 7)
