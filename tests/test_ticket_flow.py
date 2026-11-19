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

    assert list(names) == ["M1", "M2", "M3"]                     # was M1-M4 until 2026-11-16: see "earn its place" below
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


# ---------- decided 2026-11-16: a review that settles (two lists, repair checks, review-notes.md) ----------
# A live try never settled: every later review read everything again, and every doubt blocked the tick.

def reviewer_text():
    return front_matter((PLUGIN / "agents" / "code-reviewer.md").read_text(encoding="utf-8"))[1]


def line_starting(text, starts_with):
    """The one line of a file that starts with these words."""
    lines = [line for line in text.splitlines() if line.startswith(starts_with)]
    assert len(lines) == 1, f"expected one line starting with {starts_with!r}, found {len(lines)}"
    return lines[0]


REASONS = ["`wrong result`", "`broken promise`", "`live system`", "`secret`"]


def test_the_reviewer_sorts_every_finding_into_one_of_two_lists():
    """Only "must fix" blocks the tick. A review with nothing but "good to know" notes passes."""
    lists = section(reviewer_text(), "The two lists")
    writes = section(reviewer_text(), "What you write")

    assert "**Must fix**" in lists and "**Good to know**" in lists
    for reason in REASONS:                                       # wrong result, broken promise, live system, a secret
        assert reason in lists
    for heading in ("\nMUST FIX\n", "\nGOOD TO KNOW\n"):         # each list under its own heading, never mixed
        assert heading in writes
    assert "MUST FIX" in line_starting(writes, "- `VERDICT: FIX`")
    assert "GOOD TO KNOW" in line_starting(writes, "- `VERDICT: PASS`")      # notes alone do not stop the milestone


def test_a_must_fix_names_the_real_case_and_one_of_the_four_reasons():
    """Replaces "not sure, so report it": a doubt with no real case is a note, it never blocks."""
    reviewer = reviewer_text()
    lists = section(reviewer, "The two lists")

    assert "With THIS input, THIS wrong thing happens" in lists
    assert "A finding goes here only when it has both of these" in lists    # the real case AND a reason
    assert "- One of four reasons:" in lists
    assert "If you are not sure something is a bug, report it" not in reviewer
    assert "not sure" in line_starting(lists, "**Good to know**")           # the doubt has a place: the second list


def test_the_reviewer_reads_the_risk_from_the_risky_line_and_from_the_code():
    """The line clear-ticket writes, and what the code really does. Nobody is asked a new question."""
    risk = section(reviewer_text(), "How risky is the job")
    risky_line = "`RISKY: <what it changes>`"

    assert risky_line in skill_text("clear-ticket")              # clear-ticket writes it...
    assert risky_line in risk and "`requirements.md`" in risk    # ...and the reviewer reads it
    assert "What the code does" in risk
    assert "Ask nobody" in risk
    no_line = line_starting(risk, "If the code changes something live")
    assert "no `RISKY:` line" in no_line and '"must fix"' in no_line
    step_4 = section(skill_text("build-milestone"), "Step 4")
    assert "`RISKY:`" in step_4 and "Do not ask the engineer" in step_4     # the skill adds no question either


def test_the_same_weak_spot_is_sorted_by_the_risk_of_the_job():
    """A skipped row is a note in a job that only reads, and blocks in a job that changes a live system."""
    lists = section(reviewer_text(), "The two lists")

    assert "Good to know" in line_starting(lists, "- The job only reads")
    risky = line_starting(lists, "- The job is risky")
    assert "Must fix" in risky and "`live system`" in risky
    assert "contract" in line_starting(lists, "- The job only reads")       # unless the creator was promised otherwise


def test_the_bug_and_design_labels_are_gone_from_the_plugins_reviewer():
    """A doubt about the approach starts with "Approach:" and is sorted like any other finding."""
    reviewer, build = reviewer_text(), skill_text("build-milestone")

    assert not re.search(r"\b(BUG|DESIGN)\b", reviewer)
    assert "`Approach:`" in reviewer and "like any other finding" in reviewer
    for step in ("Step 4", "Step 5", "Step 6"):
        assert not re.search(r"\b(BUG|DESIGN)\b", section(build, step))
    assert "`Approach:`" in section(build, "Step 5")


def test_only_the_first_review_is_full_and_later_ones_check_the_repairs():
    """Else every review reads everything again at full strictness, and the review never settles."""
    reviewer = reviewer_text()
    check = section(reviewer, "A repair check")
    step_4, step_5 = section(skill_text("build-milestone"), "Step 4"), section(skill_text("build-milestone"), "Step 5")

    assert "Then review the rest of the changes as usual" not in reviewer
    assert "Do not review the milestone again" in check
    assert "full and strict" in step_4
    assert "three reviews at most" in step_5
    assert "two rounds" in step_5                                # the stop rule stays...
    assert "another round, split the milestone, or think the approach over" in step_5     # ...with its three ways out


def test_a_repair_check_gets_the_old_findings_and_a_diff_of_only_the_repairs():
    build = skill_text("build-milestone")
    step_4, step_5 = section(build, "Step 4"), section(build, "Step 5")

    assert "`git diff HEAD --output=.claude/review.diff`" in step_4          # review 1: everything that changed
    stage = step_5.index("`git add <file> <file> ...`")                      # the reviewed files are staged, by name...
    repairs_only = step_5.index("`git diff --output=.claude/review.diff`")   # ...so a plain diff shows the repairs only
    assert stage < repairs_only
    start = step_5[step_5.index("Start a NEW reviewer"):]
    assert "word for word" in start and "Repair check" in start
    no_git = between(step_5, "- Without `.git`:", "- Start a NEW reviewer")
    assert REVIEW_FILES in no_git and "only those files" in no_git           # no git: the files the repairs touched


def test_a_repair_check_reports_the_repairs_and_nothing_new_below_must_fix():
    check = section(reviewer_text(), "A repair check")
    step_5 = section(skill_text("build-milestone"), "Step 5")

    for words in ("`FIXED`", "`NOT FIXED`", "`broken by a repair`", "`new, outside the repairs`"):
        assert words in check                                    # the reviewer writes them...
        assert words in step_5                                   # ...and the skill knows what each one means
    assert 'No new "good to know"' in check
    assert "\nREPAIRS\n" in section(reviewer_text(), "What you write")


def test_fixing_a_good_to_know_note_needs_no_new_review_unless_the_fix_grows():
    step_5 = section(skill_text("build-milestone"), "Step 5")

    assert "only time" in step_5                                 # the engineer sees the notes once, and picks
    small = table_row(step_5, 'Only "good to know" notes, and every fix stayed small')
    grew = table_row(step_5, 'Only "good to know" notes, and a fix grew')
    assert "No new review" in small and "Step 6" in small
    # (c), 2026-11-18: was "changes code in another file than the one the note names"
    assert "A fix grew when it adds new behaviour, or touches a code file the note does not name" in grew
    assert "Tell the engineer" in grew and "repair check" in grew
    assert "repair check" in table_row(step_5, 'At least one "must fix"')


def test_what_is_not_fixed_goes_to_review_notes_and_the_log_gets_one_line():
    build = skill_text("build-milestone")
    step_5, step_6 = section(build, "Step 5"), section(build, "Step 6")

    block = review_notes_example()                               # one block per milestone
    assert "## M<n>" in block and "\nLeft as it is (the engineer's choice):\n" in block
    assert "`review-notes.md`" in step_5                         # (the shape of the block has its own test below)
    assert "review: not fixed (" not in build                    # the old way: one log line per finding

    log_lines = re.findall(r"`(2026-\d\d-\d\d — M\d[^`]*)`", step_6)
    assert any("4 notes in review-notes.md" in line for line in log_lines)
    assert any("must fix not fixed" in line and "review-notes.md" in line for line in log_lines)
    for line in log_lines:                                       # the hook still sees each one as today's tick line
        date, text = pn.last_update(line, NOW)
        assert date and re.search(r"\bM\d\b.*\b(ticked|done)\b", text, re.I)


def test_the_tick_waits_for_must_fix_findings_only():
    opening = between(section(skill_text("build-milestone"), "Step 6"), "Only when the proof is in hand", "1. If any code changed")

    assert "`VERDICT: PASS`" in opening
    assert '"must fix"' in opening and "`review-notes.md`" in opening
    assert "every finding is fixed or logged" not in opening


def test_the_milestone_commit_takes_the_review_notes():
    """Else the next session finds review-notes.md as a leftover change and stops."""
    commit_step = between(section(skill_text("build-milestone"), "Step 6"), "4. If the folder has `.git`", "5. If that was the last milestone")

    assert "`review-notes.md`" in commit_step


def test_the_common_mistakes_follow_the_new_review():
    mistakes = section(skill_text("build-milestone"), "Common mistakes")

    said_no = table_row(mistakes, "Leaving out a finding the engineer said no to")
    assert "`review-notes.md`" in said_no and "the log" not in said_no
    assert "repair checks" in table_row(mistakes, "Running the full review again after a repair, or in a new session")
    assert '"must fix"' in table_row(mistakes, 'Holding the tick for a "good to know" note')
    assert "`review-notes.md`" in table_row(mistakes, "Committing every file in the folder at once")


# ---------- review of the new review, 2026-11-16: each test below failed before its fix ----------

def test_what_a_repair_broke_holds_the_tick_only_with_a_real_case_and_a_reason():
    """Else a repair that makes a log line less clear holds the tick, and the review never settles."""
    check = section(reviewer_text(), "A repair check")
    writes = section(reviewer_text(), "What you write")
    step_5 = section(skill_text("build-milestone"), "Step 5")

    broke = line_starting(check, "2. Anything a repair broke")
    assert "a real case and one of the four reasons" in broke    # the same bar as every other "must fix"
    assert "`REPAIR NOTES`" in broke                             # below that bar it is still reported, in its own place
    assert "\nREPAIR NOTES\n" in writes
    assert "REPAIR NOTES" in line_starting(writes, "- `VERDICT: PASS`")      # and it does not change the verdict
    assert "REPAIR NOTES" not in line_starting(writes, "- `VERDICT: FIX`")
    assert "one of the four reasons" in table_row(step_5, "`broken by a repair`")
    notes_row = table_row(step_5, "`REPAIR NOTES`")
    assert "does not hold the tick" in notes_row and "picks" in notes_row    # the engineer sees it and picks


def review_notes_example():
    """The example of review-notes.md in the build-milestone skill, without the indent it has inside its list."""
    return re.sub(r"^   ", "", fenced(skill_text("build-milestone"), "# Review notes"), flags=re.M)


def test_review_notes_keeps_the_open_findings_and_the_number_of_repair_checks():
    """A later session must be able to hand the open findings to a repair check, and know which round it is."""
    example = review_notes_example()

    assert "\n## M<n> (YYYY-MM-DD)\n" in example                 # one block per milestone
    assert "\nRepair checks so far: 0\n" in example              # three reviews at most, also across sessions
    open_list = between(example, "\nOpen (", "\nLeft as it is (")
    settled = example[example.index("\nLeft as it is ("):]
    for kept in (open_list, settled):                            # each finding keeps the list the reviewer put it in
        assert "\n- MUST FIX: <the finding, word for word>" in kept
        assert "\n- GOOD TO KNOW: <the finding, word for word>" in kept
    assert "Reason" in line_starting(settled, "- MUST FIX:")     # a "must fix" nobody fixes keeps the engineer's reason
    assert "Reason" not in open_list
    assert "not fixed" not in example.lower()                    # `NOT FIXED` is the reviewer's word for a failed repair


def test_the_number_of_repair_checks_is_written_down_as_soon_as_one_comes_back():
    step_5 = section(skill_text("build-milestone"), "Step 5")

    assert "add 1 to `Repair checks so far`" in step_5
    assert "`Repair checks so far: 2`" in between(step_5, "One round is:", "If the session ends")     # the stop rule reads it


def test_the_rule_block_for_the_work_folder_follows_the_skills():
    """work_jira_rules.md is pasted into the work folder's CLAUDE.md: it must not say an older rule."""
    rules = " ".join((PLUGIN.parent / "work_jira_rules.md").read_text(encoding="utf-8").split())

    assert "listed in tracking_log.md" not in rules              # the review: only a "must fix" holds the tick
    assert 'every "must fix" is fixed, or is in review-notes.md with the user\'s reason' in rules
    assert "review-notes.md if it is there" in rules             # the milestone commit takes it
    assert "confirms in chat" not in rules                       # a user check: the user's own answer, not a yes
    assert "in their own words" in rules and "Never say the expected answer first" in rules
    assert "Too big → split" not in rules                        # a split must earn its place
    assert "only when its code truly does not fit one session" in rules
    assert "No branches in a ticket folder" in rules and "main line" in rules


# ---------- review round 2 of the new review, 2026-11-16: the test below failed before its fix ----------

def picked_up_part():
    """The part of Step 5 for a milestone an earlier session left open. It is the last part of the step."""
    step_5 = section(skill_text("build-milestone"), "Step 5")
    return step_5[step_5.index("**Picked up from an earlier session.**"):]


def test_the_engineer_is_asked_again_after_every_extra_round():
    """Else "another round" takes the count to 3, no rule fires any more, and round 4 starts unasked."""
    step_5 = section(skill_text("build-milestone"), "Step 5")

    assert "2 or more" in picked_up_part()
    stop_rule = between(step_5, "One round is:", "If the session ends")
    assert "`Repair checks so far: 2` or more" in stop_rule
    assert "after every extra round" in stop_rule


# ---------- decided 2026-11-16, after three review rounds: a simpler pick-up ----------
# Findings are saved the moment a review arrives. A later session remembers nothing about files: it asks about
# what has no answer yet, and its repair check gets the whole milestone with the order "check only these findings".
# (This replaced a `Staged since the last review` line in the block, and three tests that held it in place.)

def item(text, starts_with):
    """One bullet or numbered item of a skill, with the lines it wraps onto."""
    start = text.index("\n" + starts_with) + 1
    end = re.search(r"\n(?=\s*- |\s*\d+\. |\n)", text[start:])
    return text[start:start + end.start()] if end else text[start:]


def test_every_finding_is_saved_the_moment_a_review_comes_back():
    """Else a session that ends before the engineer answered loses the findings, or the next session takes
    them for picked and repairs them without asking."""
    step_5 = section(skill_text("build-milestone"), "Step 5")
    example = review_notes_example()

    save, tell, repair = (step_5.index(part) for part in
                          ("**Write it down first.**", "**Tell the engineer.**", "**Repair what the engineer picked.**"))
    assert save < tell < repair
    saving = step_5[save:tell]
    assert "before you tell or ask the engineer anything" in saving
    no_answer, picked, settled = (example.index(f"\n{name} (") for name in ("No answer yet", "Open", "Left as it is"))
    assert no_answer < picked < settled                          # three plain states, never mixed
    assert "\n- MUST FIX: <the finding, word for word>" in example[no_answer:picked]
    new = item(saving, "- A new finding")
    assert '"No answer yet"' in new and "word for word" in new
    answer = item(saving, "- The engineer's answer moves it")
    assert '"Open"' in answer and '"Left as it is"' in answer and "reason" in answer
    assert "`FIXED`" in item(saving, '- A finding leaves "Open"')            # fixed and checked: only then is it gone
    back = between(step_5, "As soon as it comes back", "What comes back:")
    assert "`NOT FIXED`" in back and '"No answer yet"' in back   # a repair that failed is the engineer's call again
    ends = between(step_5, "If the session ends with the milestone still open", "**Picked up")
    assert "put every finding" not in ends and "The block already holds every finding" in ends


def test_a_milestone_picked_up_again_gets_a_repair_check_and_no_new_full_review():
    """Else a break brings a whole new list of findings, and the engineer is asked about notes again."""
    row = table_row(section(skill_text("build-milestone"), "Step 0"), "The first open milestone is already built")
    picked_up = picked_up_part()

    assert "has a block for" in row and "`review-notes.md`" in row           # the full review is done: its findings are saved
    assert "Picked up from an earlier session" in row and "Step 5" in row
    assert "No block" in row and row.index("No block") < row.index("Step 4")  # the review never ran: it is still owed
    assert "do not run it again" in picked_up
    assert "`Repair checks so far`" in picked_up                 # the count of rounds survives the break


def test_a_picked_up_session_asks_about_unanswered_findings_before_it_repairs_anything():
    """Else "out of time, let's go on tomorrow" turns every finding into one the engineer picked."""
    picked_up = picked_up_part()

    ask = item(picked_up, "1. ")
    assert '"No answer yet"' in ask and "Tell the engineer" in ask
    assert "Never repair a finding the engineer did not pick" in ask
    assert "repair it now" in item(picked_up, "2. ")             # the repairs come second


def test_no_session_trusts_what_an_earlier_session_staged():
    """Else a file changed by hand between two sessions is staged as "seen by the last review", stays out of
    the repair check's diff, and is committed with no reviewer ever having it in front of it."""
    build = skill_text("build-milestone")
    row = table_row(section(build, "Step 0"), "The first open milestone is already built")
    picked_up = picked_up_part()

    assert "Staged since the last review" not in build           # nothing about files is remembered across sessions
    assert "stage" not in row.lower()                            # Step 0 stages nothing
    assert "Stage nothing" in item(picked_up, "2. ")
    always = item(picked_up, "3. ")
    assert "whatever the table above says" in always and "`none`" in always  # at least one check before the tick...
    assert "by hand" in always and "Step 3" in always            # ...because the code may have changed since the last one
    whole = picked_up[picked_up.index("Every repair check in this session"):]
    assert "the first one too" in whole and "WHOLE milestone" in whole
    assert "`git add -N`" in whole and "`git diff HEAD --output=.claude/review.diff`" in whole
    assert REVIEW_FILES in whole and "whole list" in whole       # without git: every file of the milestone
    assert "not only the repairs" in whole and "Check only these findings" in whole     # the reviewer is told what it holds


def test_the_reviewer_can_do_a_repair_check_on_the_whole_milestone():
    check = section(reviewer_text(), "A repair check")

    assert "unless your task says they hold the whole milestone" in check    # only the repairs, or all of it
    assert "Do not review the milestone again" in check
    assert "do not take the rest of the milestone for a repair" in check
    assert '"Repair check"' in line_starting(reviewer_text(), "There are two kinds of review.")   # also with no old findings


def test_the_tick_waits_until_every_finding_has_an_answer():
    opening = between(section(skill_text("build-milestone"), "Step 6"), "Only when the proof is in hand", "1. If any code changed")

    assert '"No answer yet"' in opening and '"Open"' in opening and "`none`" in opening


# ---------- the last review round, 2026-11-16: each test below failed before its fix ----------

def test_after_two_repair_checks_the_engineer_is_asked_before_any_further_one():
    """Else a note fix that grew, with no "must fix" open, starts repair check 3, 4, ... without asking."""
    step_5 = section(skill_text("build-milestone"), "Step 5")
    ask_first = "says 2 or more, ask the engineer first"

    assert ask_first in between(step_5, "**The repair check.**", "- With `.git`:")   # a session with no break...
    assert ask_first in picked_up_part()                                             # ...reads the same as a picked-up one
    assert "whatever is open" in between(step_5, "One round is:", "If the session ends")


def test_the_rule_block_holds_the_tick_until_every_finding_has_an_answer():
    """Else a review that passed with notes is ticked before the engineer got to pick."""
    rules = " ".join((PLUGIN.parent / "work_jira_rules.md").read_text(encoding="utf-8").split())

    assert "answered every finding" in rules
    assert '"No answer yet"' in rules and '"Open"' in rules      # the same two lists Step 6 of build-milestone reads


def test_a_clean_milestone_closes_after_two_rounds_with_no_question():
    """Else a clean `VERDICT: PASS` at the second repair check meets "Stop, and ask: split or think it over?"."""
    step_5 = section(skill_text("build-milestone"), "Step 5")
    stop_rule = between(step_5, "One round is:", "If the session ends")

    assert "Stop. Tell the engineer" not in stop_rule            # the stop has its condition again...
    assert 'If a repair check would be next, or a "must fix" is still open, stop.' in stop_rule
    # ...and when it does not hold, the stop rule says nothing: it sends nothing to Step 6, in any words
    assert "Step 6" not in stop_rule
    assert "Neither one" not in stop_rule and "with no question" not in stop_rule
    assert "start no repair check on your own" in stop_rule and "whatever is open" in stop_rule   # that part stays
    # the list above the stop rule decides, at any count: a clean milestone closes, notes reach the engineer
    after_a_check = between(step_5, "What comes back:", "One round is:")
    assert '\n- Nothing is under "No answer yet": go to Step 6.\n' in after_a_check
    notes = " ".join(item(after_a_check, "- Something is:").split())
    assert "tell the engineer in one message" in notes and "move each finding by their answer" in notes
    assert "After `VERDICT: PASS` none of it holds the tick" in notes        # a PASS with notes still asks


# ---------- decided 2026-11-16, after a live try on a made-up ticket: five wording faults ----------

def one_line(text):
    """The text with every run of spaces and line breaks turned into one space, so a wrapped rule reads as one line."""
    return " ".join(text.split())


def rules(name):
    """The "Rules for the whole skill" block of a skill, as one line."""
    return one_line(section(skill_text(name), "Rules for the whole skill"))


# -- a milestone must earn its place (the try planned 7 milestones for a 100-line script) --

def test_a_milestone_must_earn_its_place():
    """Four things earn a milestone. The rest is ONE build milestone: cutting by function earns nothing."""
    plan = skill_text("plan-milestones")             # not section(): the example in Step 4 has a `## ` line of its own
    rule = one_line(between(plan, "- **One session each", "- **A proof each.**"))

    assert "earns its place" in rule
    for earns in ("one real sample", "a dry run", "a check only the engineer can do", "truly does not fit one session"):
        assert earns in rule
    assert "ONE build milestone" in rule
    assert "Cutting by function earns nothing" in rule


def test_the_milestone_example_has_one_build_milestone_and_the_engineers_checks():
    """The example is what Claude copies: a short read-only script is not cut into read, find and write."""
    lines = [line for line in milestone_example(skill_text("plan-milestones")).splitlines() if line.startswith("- [ ]")]

    with_code = [line for line in lines if "test_" in line]
    checks = [line for line in lines if "user check" in line]

    assert len(with_code) == 1                                   # ONE build milestone, with all its tests
    assert with_code[0].count("test_") == 6
    assert len(checks) == len(lines) - 1 == 2                    # the real sample, and the check only the engineer can do


def test_plan_milestones_no_longer_says_split_when_unsure():
    plan = skill_text("plan-milestones")

    assert "Unsure: split it" not in plan
    assert "the whole script" not in plan                        # the old mistake row said: split it
    assert "Unsure" in one_line(section(plan, "Step 6")) and "keep it as one" in one_line(section(plan, "Step 6"))
    assert "ONE build milestone" in table_row(plan, "A milestone for each function")
    too_big = between(section(skill_text("build-milestone"), "Step 0"), "**Too big?**", "**The log.**")
    assert "truly" in too_big                                    # the build session splits for size only, like the plan


def test_the_price_is_said_before_the_engineer_approves():
    plan = skill_text("plan-milestones")
    step_7 = section(plan, "Step 7")

    assert "`<N> milestones = <N> sessions, <R> reviews`" in step_7
    assert step_7.index("sessions, <R> reviews") < step_7.index('"Do you approve this plan?"')
    assert "price" in section(plan, "Changing the plan later")   # a changed plan is approved again, so it has a price too


# -- no branches in a ticket folder (the try made a branch nobody planned) --

@pytest.mark.parametrize("name", ["plan-milestones", "build-milestone"])
def test_the_skills_that_commit_say_no_branch_and_the_main_line(name):
    said = rules(name)

    assert "**No branches in a ticket folder.**" in said
    assert "straight on the main line" in said
    assert "Never make, switch, merge or delete a branch by yourself" in said
    assert "never switch to one" not in said                     # review 2026-11-16: that also forbade what the engineer asks for
    assert "even when the engineer's own rules say" in said      # it wins over a personal "work goes on a branch" rule


@pytest.mark.parametrize("name", SKILLS)
def test_no_skill_makes_or_switches_a_branch(name):
    text = skill_text(name)

    for command in ("git checkout", "git switch", "git branch"):
        assert command not in text


# -- who decides the steps (the try got two plans and two reviewers: the plugin's and the engineer's own) --

STEPS_RULE = ("**This plugin decides the steps in a ticket folder:** plan, review, tick, commit, close. "
              "The engineer's own rules, skills and agents for planning, reviewing, committing or closing work "
              "stay quiet here")


@pytest.mark.parametrize("name", SKILLS)
def test_every_skill_says_the_plugin_decides_the_steps_and_own_code_rules_still_count(name):
    said = rules(name)

    assert STEPS_RULE in said                                    # the same line in all three: each skill is read alone
    assert "HOW code is written" in said and "still count" in said


@pytest.mark.parametrize("name", SKILLS)
def test_no_skill_names_one_persons_own_skills(name):
    """Colleagues have other skills: the rule is about kinds of rules, not about one person's list."""
    for own in ("grill-me", "close-out", "model-advice"):
        assert own not in skill_text(name)


# -- a user check: the engineer says what they see, before Claude says what was expected --

def test_a_user_check_asks_an_open_question_and_never_says_the_answer_first():
    build = skill_text("build-milestone")
    step_3 = one_line(section(build, "Step 3"))

    assert "what they should see" not in build                   # the old row told Claude to say the answer first
    assert "Ask an open question" in step_3
    assert "Never say the expected answer first" in step_3
    assert "Compare only after their answer" in step_3
    assert step_3.index("Ask an open question") < step_3.index("Compare only after their answer")
    assert "In every user check" in step_3                       # a general rule, not only for counts
    assert "an answer you said first" in step_3                  # a "yes" to it is in the "not proof" list
    assert "ask what they see" in table_row(build, "Saying what a user check should show")


def test_a_user_check_line_in_the_plan_does_not_give_the_answer_away():
    """build-milestone reads "Done when" out to the engineer: an answer written there is said first."""
    plan = skill_text("plan-milestones")

    assert "never the answer itself" in one_line(between(plan, "- **A proof each.**", "- **No `<angle"))
    assert "what they see" in table_row(plan, "A user check line that gives the answer")


# -- the proof of a yes says only what really happened (the try wrote "confirmed, no but", and nobody had asked) --

def test_the_proof_of_the_creators_yes_has_two_labels_and_no_check_nobody_made():
    clear = skill_text("clear-ticket")
    step_8 = one_line(section(clear, "Step 8"))

    assert "Pasted:\n" in fenced(clear, "## The creator's yes")
    assert "`Told by <engineer>: <what the creator said>`" in step_8
    assert "the only two labels" in step_8
    assert "says only what really happened" in step_8
    assert 'unless you asked it in this chat and the engineer answered' in step_8
    assert "only when you asked and the engineer answered" in step_8          # said at the question too, not only at the proof
    step_6 = one_line(section(clear, "Step 6"))
    assert "pasted from Slack" in step_6 and "told by Sam" in step_6 and "Only two labels" in step_6
    assert "only if you asked" in table_row(clear, 'Writing "confirmed, no but"')


def test_closing_a_ticket_writes_only_what_really_happened():
    """The same proof, at the end of the ticket: pasted, told by the engineer, or closed by the engineer."""
    build = skill_text("build-milestone")
    closing = one_line(section(build, "Closing the ticket"))

    assert "Pasted:\n" in fenced(build, "## Closed")
    assert "`Told by <engineer>: <what the creator said>`" in closing
    assert "say only what really happened" in closing
    assert 'unless you asked it in this chat and the engineer answered' in closing
    assert "`YYYY-MM-DD — ticket closed by <engineer>`" in closing           # not "confirmed by" when nobody confirmed


# ---------- review findings, 2026-11-16: each test below failed before its fix ----------

def test_the_engineers_own_idea_has_a_proof_line_that_is_true():
    """Nobody pasted or retold anything, so neither of the two labels fits: the yes was said in this chat."""
    clear = skill_text("clear-ticket")
    own_idea = one_line(section(clear, "No ticket"))

    assert "neither `Pasted:` nor `Told by <engineer>:`" in own_idea
    assert "`Said in this chat: <the engineer's own words>`" in own_idea
    assert "`(own project, <name>, <date>)`" in own_idea
    step_8 = one_line(section(clear, "Step 8"))
    assert "the only two labels for a reply the engineer brings" in step_8     # so the two rules no longer disagree
    assert 'see "No ticket"' in step_8


def test_an_old_plan_is_not_approved_without_its_price():
    """The price comes before every yes to a plan, also the one for milestones from before the plugin."""
    row = table_row(section(skill_text("plan-milestones"), "Step 0"), "Milestone lines from before this skill")

    assert "price" in row and "Step 7" in row
    assert row.index("price") < row.index('"Do you approve these milestones as the plan?"')
    assert "already ticked" in row                               # part of that price is paid: say how much


@pytest.mark.parametrize("name", ["plan-milestones", "build-milestone"])
def test_a_folder_on_another_branch_is_reported_and_nothing_is_done_alone(name):
    """Decided 2026-11-16: check the branch at the start. Not on the main line: say what is there, ask, do nothing alone."""
    step_0 = section(skill_text(name), "Step 0")
    check = one_line(step_0[step_0.index("**The branch.**"):])

    assert "`git status`" in check                               # its first line names the branch
    assert "do nothing by yourself" in check
    assert "which branch the folder is on" in check and "what is on it" in check
    assert "ask what to do" in check
    assert "Do not go on until that is settled" in check
    assert "Then do what the engineer says" in check             # their answer is carried out: the skill does not forbid it
    assert "Step 0" in rules(name)                               # the rule points at the check


def test_the_branch_check_in_build_milestone_is_for_every_row_that_goes_on():
    """The closing commits and a milestone that waits for its review also commit: not only an open milestone."""
    step_0 = section(skill_text("build-milestone"), "Step 0")

    assert step_0.index("| There is an open milestone |") < step_0.index("**The branch.**")
    assert step_0.index("**The branch.**") < step_0.index("Only when you took the last row")


def test_clear_ticket_commits_nothing_so_it_needs_no_branch_check():
    assert "git commit" not in skill_text("clear-ticket")


# ---------- decided 2026-11-18: seven wording points (a-g), each test below failed before its fix ----------

def test_claude_never_adds_the_risky_line_itself_to_settle_a_finding():
    """Else "no RISKY: line" is repaired by writing one, and a job that changes a live system gets no dry run."""
    step_5 = one_line(section(skill_text("build-milestone"), "Step 5"))

    assert "Never add a `RISKY:` line yourself" in step_5
    assert "the job turned out risky" in step_5                  # Claude stops and says so...
    assert "dry run" in step_5 and "`ticket-flow:plan-milestones`" in step_5     # ...and the plan gets its dry run
    row = table_row(section(skill_text("plan-milestones"), "Changing the plan later"), "The job turned out risky")
    assert "The engineer decides" in row and "dry run" in row    # the normal planning path takes it from there


def test_a_test_that_reads_a_live_system_is_a_must_fix_in_every_job():
    """Decided: also in a job that only reads. The one real sample of M1 is a check by hand, not a test."""
    live = line_starting(section(reviewer_text(), "The two lists"), "  - `live system`")

    assert "test that reads a live system" in live
    assert "every job" in live and "only reads" in live
    assert "test that reads a live system" in table_row(section(skill_text("build-milestone"), "Step 5"), "`MUST FIX`")
    sample = one_line(between(skill_text("plan-milestones"), "- **M1 is one real sample**", "- **The riskiest part early.**"))
    assert "Its proof is a user check" in sample                 # M1 stays as it is


def test_a_user_check_gets_its_own_milestone_only_when_the_build_session_cannot_hold_it():
    """Else every check the engineer could do on the spot costs one more session."""
    plan = skill_text("plan-milestones")
    rule = one_line(between(plan, "- **One session each", "- **A proof each.**"))

    assert "rides on the build milestone" in rule
    assert "a real run at work, another day, or another person" in rule
    assert "Only four things earn a milestone of their own" in rule          # still four: Step 6 counts on it


def test_the_engineers_own_project_is_not_asked_about_a_but():
    """There is no creator, so nobody retold a yes that could have dropped a "but"."""
    step_8 = one_line(section(skill_text("clear-ticket"), "Step 8"))
    part_2 = one_line(between(skill_text("build-milestone"), "**Part 2: the reply.**", "| What comes back"))

    assert "skip this question" in step_8 and 'see "No ticket"' in step_8
    assert "own project" in part_2 and "skip this question" in part_2


def test_after_two_rounds_the_findings_and_the_round_question_come_in_one_message():
    """Else the engineer answers "which ones do I fix?", and is asked "another round?" right after."""
    step_5 = section(skill_text("build-milestone"), "Step 5")
    stop_rule = one_line(between(step_5, "One round is:", "If the session ends"))

    assert "in ONE message" in stop_rule
    ask = one_line(item(picked_up_part(), "1. "))                # a picked-up session always has a repair check next
    assert "2 or more" in ask and "same message" in ask


def test_the_approval_of_an_old_plan_is_committed_by_name():
    """Else the first build session finds requirements.md as a leftover change and stops."""
    row = table_row(section(skill_text("plan-milestones"), "Step 0"), "Milestone lines from before this skill")

    assert "`git add requirements.md`" in row and "git commit" in row and "Never push" in row
    assert "Step 7, item 3" in row                               # the same way the plan commit does it
    assert row.index("add the `Plan approved by` line") < row.index("git commit") < row.index("starts in a new session")
