"""The ticket-flow plugin's skill and agent files: the parts that other code, or another skill, depends on.

Skills are instructions, not code, so most of their wording is checked by a live try. These tests only
guard the few lines that must stay exact: the milestone lines the dashboard reads, the words one skill
writes and the next one looks for, and the reviewer staying read-only.
"""
import re
from pathlib import Path

import pytest

import project_note as pn

PLUGIN = Path(__file__).resolve().parent.parent / "ticket-flow"
SKILLS = ["clear-ticket", "plan-milestones", "build-milestone"]


def skill_text(name):
    return (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def front_matter(text):
    """The `key: value` lines between the first two `---` lines, as a dict, plus the body below them."""
    _, head, body = text.split("---\n", 2)
    fields = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, body


def milestone_example(text):
    """The first fenced example in a skill that holds a `## Milestones` heading."""
    for block in re.findall(r"```markdown\n(.*?)```", text, flags=re.S):
        if "## Milestones" in block:
            return block
    raise AssertionError("no fenced example with a '## Milestones' heading")


@pytest.mark.parametrize("name", SKILLS)
def test_skill_file_keeps_inside_the_claude_code_limits(name):
    fields, body = front_matter(skill_text(name))

    assert fields["name"] == name                      # the folder name is how the skill is called
    assert 0 < len(fields["description"]) <= 1024      # longer descriptions are cut off
    assert len(body.splitlines()) < 500


def test_the_dashboard_can_read_the_milestone_example_in_plan_milestones():
    example = milestone_example(skill_text("plan-milestones"))

    names = pn.milestone_names(example)
    ticked = pn.read_milestones(example)

    assert list(names) == ["M1", "M2", "M3", "M4"]
    assert names["M1"] == "look at one real export file"
    assert all(names.values())                                   # every milestone has a short name for the card
    assert not any("Done when" in name for name in names.values())
    assert not any(ticked.values())                              # a new plan starts with nothing ticked


def test_the_milestone_template_line_is_not_taken_for_a_real_milestone():
    template = "- [ ] M1 — <what it delivers> · Done when: <proof>"

    assert template in skill_text("plan-milestones")
    assert pn.read_milestones(template) == {}


@pytest.mark.parametrize("name", SKILLS)
def test_every_skill_uses_the_same_words_for_the_creators_yes(name):
    assert "CONFIRMED BY CREATOR" in skill_text(name)            # clear-ticket writes it, the other two check it


@pytest.mark.parametrize("name", ["plan-milestones", "build-milestone"])
def test_planning_and_building_use_the_same_words_for_an_approved_plan(name):
    assert "Plan approved by" in skill_text(name)                # plan-milestones writes it, build-milestone checks it


def test_build_milestone_starts_the_plugins_own_reviewer():
    assert "ticket-flow:code-reviewer" in skill_text("build-milestone")


def test_the_reviewer_can_only_read():
    fields, body = front_matter((PLUGIN / "agents" / "code-reviewer.md").read_text(encoding="utf-8"))

    assert fields["name"] == "code-reviewer"
    assert fields["tools"] == "Read, Grep, Glob"                 # no Edit, Write or Bash: it can never fix or run
    assert "model" not in fields                                 # it runs on the session's model (decided 2026-11-15)
    assert "VERDICT: PASS" in body and "VERDICT: FIX" in body


# ---------- review findings, 2026-11-15: each test below failed before its fix ----------

def section(text, heading):
    """The text of one `## ` section of a skill, from its heading to the next `## ` heading."""
    start = text.index("\n## " + heading)
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else len(text)]


def table_row(text, starts_with):
    """The one table row of a skill whose first cell starts with these words."""
    rows = [line for line in text.splitlines() if line.startswith("| " + starts_with)]
    assert len(rows) == 1, f"expected one table row starting with {starts_with!r}, found {len(rows)}"
    return rows[0]


def test_build_milestone_knows_a_closed_ticket_and_a_result_that_waits_for_the_creator():
    """All milestones ticked is three different moments: closed, waiting for the reply, or nothing sent yet."""
    step_0 = section(skill_text("build-milestone"), "Step 0")

    closed = step_0.index("`## Closed`")
    waiting = step_0.index("to confirm the result")
    nothing_sent = step_0.index("| Every milestone is ticked |")

    assert closed < waiting < nothing_sent          # "take the first row that fits": the special cases come first
    assert "Part 2" in table_row(step_0, "Every milestone is ticked, and")
    assert "Part 1" in table_row(step_0, "Every milestone is ticked |")


def test_a_result_the_creator_did_not_accept_takes_the_ticket_out_of_waiting():
    """Else the card keeps saying "waiting for the creator" while the missing milestone is built."""
    row = table_row(skill_text("build-milestone"), '"It does not do X", and X is in the contract')

    assert "PENDING" in row                          # the waiting line comes out of tracking_log.md
    assert "3-Build" in row                          # and the Phase goes back from 5-Handover


@pytest.mark.parametrize("name", SKILLS)
def test_no_skill_commits_files_nobody_looked_at(name):
    """`git add .` would commit data files and logins that were kept out of the review on purpose."""
    assert "git add ." not in skill_text(name)


def between(text, start, end):
    """The text from one marker up to the next one."""
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def test_the_checks_before_building_are_only_for_an_open_milestone():
    """Else a ticket that waits for the creator's reply gets its waiting line "fixed" away."""
    step_0 = section(skill_text("build-milestone"), "Step 0")

    last_table_row = step_0.index("| There is an open milestone |")
    only_then = step_0.index("Only when you took the last row")
    first_check = step_0.index("**Leftover changes.**")

    assert last_table_row < only_then < first_check


def test_every_edit_the_skills_make_outside_a_milestone_is_committed():
    """Else the next session finds its own files as "leftover changes" and stops."""
    build = skill_text("build-milestone")
    plan = skill_text("plan-milestones")

    assert "git commit" in between(build, "**Part 1: show the creator.**", "**Part 2: the reply.**")
    assert "git commit" in table_row(build, '"It does not do X", and X is in the contract')
    assert "git commit" in section(plan, "Changing the plan later")


@pytest.mark.parametrize("name", ["ticket.md", ".gitignore", "CLAUDE.md"])
def test_the_plan_commit_takes_the_files_the_first_skill_made(name):
    """clear-ticket writes these and commits nothing. Left out, the first build session stops on them."""
    commit_step = between(section(skill_text("plan-milestones"), "Step 7"), "4. If the folder has `.git`", "5. Tell the engineer")

    assert "git status" in commit_step               # it looks at what is new or changed, it does not guess
    assert f"`{name}`" in commit_step


def test_a_milestone_that_is_built_but_not_reviewed_goes_straight_to_the_review():
    """Else the next session starts the finished milestone again from its first test."""
    build = skill_text("build-milestone")
    step_0 = section(build, "Step 0")

    row = table_row(step_0, "The first open milestone is already built")

    assert step_0.index(row) < step_0.index("| There is an open milestone |")     # first row that fits wins
    assert "waiting for review" in row and "Step 4" in row
    assert "waiting for review" in section(build, "Step 4")                       # the line that row looks for...
    assert "waiting for review" in section(build, "Step 5")                       # ...is written at both stops


def test_the_dashboard_can_read_the_goal_from_the_ticket_file_clear_ticket_writes(tmp_path):
    text = skill_text("clear-ticket")
    layout = next(block for block in re.findall(r"```markdown\n(.*?)```", text, flags=re.S)
                  if pn.DESCRIPTION_HEADING in block)
    assert "<the pasted text, unchanged>" in layout
    (tmp_path / pn.TICKET).write_text(layout.replace("<the pasted text, unchanged>", "Report the late orders."),
                                      encoding="utf-8")

    assert pn.ticket_goal(tmp_path) == "Report the late orders."
