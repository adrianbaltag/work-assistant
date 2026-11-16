"""The ticket-flow plugin's skill and agent files: the parts that other code, or another skill, depends on.

Skills are instructions, not code, so most of their wording is checked by a live try. These tests only
guard the few lines that must stay exact: the milestone lines the dashboard reads, the words one skill
writes and the next one looks for, and the reviewer staying read-only.
"""
import re
from pathlib import Path

import pytest

import notes
import project_note as pn
import work_jira_hooks as hooks
from test_project_note import LOG, NOW, fields_of, projects, work_project

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
    assert "`## Now working on`" in row              # and the new milestone takes its place
    # (until 2026-11-15 this row also set the Phase line back to 3-Build: the Phase line is gone, see below)


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
    commit_step = between(section(skill_text("plan-milestones"), "Step 7"), "3. If the folder has `.git`", "4. Tell the engineer")

    assert "git status" in commit_step               # it looks at what is new or changed, it does not guess
    assert f"`{name}`" in commit_step


def test_a_milestone_that_is_built_but_not_reviewed_is_not_built_again():
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


# ---------- the 2 findings left open on 2026-11-15: a milestone that waits for its review ----------

REVIEW_FILES = "`.claude/review-files.txt`"


def test_a_milestone_picked_up_again_is_proved_again_before_its_review():
    """Else a suite that fails by now, or a user check nobody repeated, goes to the reviewer as "proved"."""
    row = table_row(section(skill_text("build-milestone"), "Step 0"), "The first open milestone is already built")

    assert "Step 3" in row and "user check" in row
    assert row.index("Step 3") < row.index("Step 4")             # the proof first, then the review


def test_without_git_the_list_of_changed_files_is_kept_for_a_later_session():
    """Else a session that picks the milestone up changed nothing itself, and its reviewer gets no files."""
    build = skill_text("build-milestone")
    no_git = between(section(build, "Step 4"), "Without `.git`", "2. **Start a fresh")

    assert REVIEW_FILES in no_git                                # saved in a file, not kept in the session's head
    assert REVIEW_FILES in table_row(build, "The first open milestone is already built")
    assert REVIEW_FILES in section(build, "Step 5")              # a fix round brings the list up to date
    assert REVIEW_FILES in section(build, "Step 6")              # taken away at the tick: the next milestone starts clean


# ---------- 2026-11-15, the hooks move into the plugin: the skills and the hooks must use the same words ----------

@pytest.mark.parametrize("name", SKILLS)
def test_no_skill_keeps_a_phase_line_up_to_date(name):
    """The Phase line is gone (decided 2026-11-15): the hooks read the next step from the ticket's files."""
    assert "Phase" not in skill_text(name)


def test_every_skill_and_agent_the_hooks_name_is_in_the_plugin():
    source = Path(hooks.__file__).read_text(encoding="utf-8")
    named = set(re.findall(r"ticket-flow:([a-z-]+)", source))
    have = set(SKILLS) | {f.stem for f in (PLUGIN / "agents").glob("*.md")}

    assert named == have                             # all four are named, and nothing that does not exist
    for old in ("clear-requirements", "grill-me", "writing-plans", "/code-review low", "/close-out", "git add ."):
        assert old not in source


def fenced(text, holds):
    """The first fenced markdown example in a skill that holds these words."""
    return next(block for block in re.findall(r"```markdown\n(.*?)```", text, flags=re.S) if holds in block)


def ticket_with(tmp_path, requirements):
    work = work_project(tmp_path)
    (work / "requirements.md").write_text(requirements, encoding="utf-8")
    return work


def test_the_gate_reads_the_status_lines_exactly_as_clear_ticket_writes_them(tmp_path):
    clear = skill_text("clear-ticket")
    waiting = fenced(clear, "WAITING FOR CREATOR")
    confirmed = waiting.replace("**Status:** WAITING FOR CREATOR (since YYYY-MM-DD)",
                                re.sub(r"^ +", "", fenced(clear, "CONFIRMED BY CREATOR"), flags=re.M))
    assert "WAITING" not in confirmed

    work = ticket_with(tmp_path, waiting)
    assert hooks.ticket_state(work) == "waiting"
    (work / "requirements.md").write_text(confirmed, encoding="utf-8")
    assert hooks.ticket_state(work) == "plan"


def test_the_gate_reads_the_plan_and_the_end_exactly_as_the_skills_write_them(tmp_path):
    plan, build = skill_text("plan-milestones"), skill_text("build-milestone")
    approved_line = "Plan approved by <engineer> (YYYY-MM-DD)"
    assert f"`{approved_line}`" in plan
    confirmed = "**Status:** CONFIRMED BY CREATOR (2026-11-15)\n\n"
    milestones = milestone_example(plan)
    approved = milestones.replace("## Milestones\n", f"## Milestones\n{approved_line}\n")

    work = ticket_with(tmp_path, confirmed + milestones)
    assert hooks.ticket_state(work) == "plan"                    # a draft: the engineer did not approve it yet
    (work / "requirements.md").write_text(confirmed + approved, encoding="utf-8")
    assert hooks.ticket_state(work) == "build"
    all_ticked = confirmed + approved.replace("- [ ]", "- [x]")
    (work / "requirements.md").write_text(all_ticked, encoding="utf-8")
    assert hooks.ticket_state(work) == "done"
    closed = re.sub(r"^ +", "", fenced(build, "## Closed"), flags=re.M)
    (work / "requirements.md").write_text(all_ticked + "\n" + closed, encoding="utf-8")
    assert hooks.ticket_state(work) == "closed"
    as_in_the_skill = fenced(build, "## Closed")                 # with the indent the example has inside its list
    assert as_in_the_skill.startswith("   ## Closed")
    (work / "requirements.md").write_text(all_ticked + "\n" + as_in_the_skill, encoding="utf-8")
    assert hooks.ticket_state(work) == "closed"


def test_a_ticket_planned_before_the_plugin_gets_its_approval_line_without_a_new_plan():
    """Else an old ticket in the middle of its milestones is stopped by the gate with no skill to open it."""
    step_0 = section(skill_text("plan-milestones"), "Step 0")
    row = table_row(step_0, "Milestone lines from before this skill")

    assert "Plan approved by" in row and "Ask once" in row and "nothing else" in row
    assert step_0.index(row) < step_0.index("| Milestone lines, but no `Plan approved by` line")    # first row that fits
    old_ticket = table_row(section(skill_text("clear-ticket"), "Step 0"), "Real content but no Status line")
    assert "Ask once" in old_ticket and "CONFIRMED" in old_ticket


# ---------- the card: "waiting for the creator" needs no new button, the PENDING line already shows ----------

def pending_lines():
    """Every `PENDING (creator, ...)` line the skills tell Claude to write, filled in with made-up words."""
    clear, build = skill_text("clear-ticket"), skill_text("build-milestone")
    templates = re.findall(r"`(PENDING \(creator, YYYY-MM-DD\): [^`]+)`", clear + build)
    assert len(templates) == 2                                   # waiting for answers, waiting for the result
    confirm = re.search(r"`(waiting for <name> to confirm the real issue\.)`", clear).group(1)
    templates.append("PENDING (creator, YYYY-MM-DD): " + confirm)
    return [t.replace("YYYY-MM-DD", "2026-11-15").replace("<name>", "Maria").replace("<N>", "3") for t in templates]


def test_every_waiting_line_the_skills_write_shows_on_the_card_as_pending_with_its_reason(tmp_path):
    lines = pending_lines()
    assert [pn.status_from(line) for line in lines] == [
        ("pending", "waiting for Maria to answer 3 questions."),
        ("pending", "waiting for Maria to confirm the result."),
        ("pending", "waiting for Maria to confirm the real issue."),
    ]
    work = work_project(tmp_path, log=LOG.replace("M2 — parse the alarm file\nand write its tests.", lines[0]))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    assert fields_of(card)["status"] == "pending"
    assert fields_of(card)["blocked_by"] == "waiting for Maria to answer 3 questions."      # the card's "Blocked by"


def test_after_the_creators_yes_the_card_is_active_again(tmp_path):
    after_yes = "Plan the milestones"
    assert f"`{after_yes}`" in skill_text("clear-ticket")
    work = work_project(tmp_path, log=LOG.replace("M2 — parse the alarm file\nand write its tests.", after_yes))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    assert fields_of(card)["status"] == "active" and fields_of(card)["blocked_by"] == ""


# ---------- decided 2026-11-15: a closed ticket stays closed, a new wish is a new ticket in its own folder ----------

def test_every_skill_sends_a_new_wish_on_a_closed_ticket_to_a_new_folder():
    """Else the hooks say "start with clear-ticket", clear-ticket says "already confirmed", and nobody can go on."""
    clear_0 = section(skill_text("clear-ticket"), "Step 0")
    closed_row = table_row(clear_0, "`requirements.md` has a `## Closed` section")
    assert "own folder" in closed_row and "stop" in closed_row.lower()
    assert clear_0.index(closed_row) < clear_0.index("| `**Status:** CONFIRMED BY CREATOR`")   # a closed file has both

    # review finding 2026-11-15: plan-milestones had no such row, so a milestone could be added to a closed ticket
    plan_0 = section(skill_text("plan-milestones"), "Step 0")
    plan_row = table_row(plan_0, "`requirements.md` has a `## Closed` section")
    assert "own folder" in plan_row and "stop" in plan_row.lower() and "No milestone" in plan_row
    assert plan_0.index(plan_row) < plan_0.index("| `**Status:** CONFIRMED BY CREATOR`")       # a closed file has both

    build = skill_text("build-milestone")
    assert "own folder" in table_row(section(build, "Step 0"), "`requirements.md` has a `## Closed` section")
    assert "own folder" in table_row(build, '"Yes, but can it also ..."')
    assert "own folder" in hooks.STEPS["closed"]
