"""Tests for what the Windows live try showed (2026-11-20, a made-up ticket through the real plugin).

1 + 2. No way round the gate: Claude never offers "write it anyway", and never writes the stopped file
       another way (a shell command). Said at session start, in the stop message and in the rule block.
3.     A user check needs the engineer's own words: output that lands in the chat (a `!` command, a paste)
       is shown, not checked.
4.     An older folder (started before ticket-flow) is asked everything in ONE message, with one answer.
       The hook and the skills use the same questions.

All folders are fake (tmp_path), all IDs and names are made up, nothing touches the network.
"""
import pytest

import work_jira_hooks as hooks
from test_project_note import work_project
from test_ticket_flow import one_line, section, skill_text, table_row
from test_ticket_gate import (ALL_TICKED, CLOSED, CONFIRMED, DRAFT, OLD, OLD_NO_MILESTONES, PLANNED, WAITING,
                              ticket, write)
from test_two_way_hooks import rule_block
from test_work_jira_hooks import begin, setup

CREATOR = "Did the creator confirm what this ticket is about?"
BUT = 'Did they add any "but" or extra wish?'
NAME = "What is the creator's name?"
APPROVE = "Do you approve these milestones as the plan?"


# ---------- findings 1 + 2: no way round the gate ----------

@pytest.mark.parametrize("reqs", [None, WAITING, DRAFT, ALL_TICKED, CLOSED, OLD, OLD_NO_MILESTONES])
def test_every_gate_stop_says_there_is_no_way_round_it(tmp_path, reqs):
    """On Windows Claude offered "write it anyway" in a menu, then wrote the file with a shell command."""
    settings, work = ticket(tmp_path, reqs)
    message = write(settings, work / "report.py")

    assert message.startswith("Not written")
    assert 'do not offer to "write it anyway"' in message
    assert "shell command" in message
    assert "say no once" in message                              # also when the user asks for it themselves
    assert message.endswith("Tell the user this in one plain sentence.")


@pytest.mark.parametrize("reqs", [None, CONFIRMED, PLANNED, ALL_TICKED, CLOSED, OLD, OLD_NO_MILESTONES])
def test_session_start_in_a_ticket_folder_says_the_gate_has_no_way_round(tmp_path, reqs):
    settings, work = ticket(tmp_path, reqs)
    (work / ".git").mkdir()
    context, _ = begin(settings, work)

    assert 'never offer the user a way round' in context and '"write it anyway"' in context
    assert "shell command" in context and "say no once" in context
    assert "Not written" not in context                          # nothing was stopped yet


@pytest.mark.parametrize("files", [["ticket.md"], ["notes.md", "query.sql"]])
def test_session_start_in_a_folder_that_is_not_set_up_says_it_too(tmp_path, files):
    """A new folder, and a folder without tracking_log.md: the gate works there from the first minute."""
    settings, _ = setup(tmp_path)
    work = work_project(tmp_path, log=None, files=files)
    context, _ = begin(settings, work)

    assert 'never offer the user a way round' in context and "shell command" in context


def test_the_rule_block_says_the_gate_has_no_way_round():
    rules = one_line(rule_block())

    assert 'Never offer a way round it ("write it anyway")' in rules
    assert "shell command" in rules and "say no once" in rules


# ---------- finding 3: output in the chat is shown, not checked ----------

def test_output_in_the_chat_does_not_pass_a_user_check_by_itself():
    """On Windows a `!` command's output passed the check: the engineer never said what they saw."""
    step_3 = one_line(section(skill_text("build-milestone"), "Step 3"))
    check = step_3[step_3.index("**A user check.**"):step_3.index("These are not proof:")]
    not_proof = step_3[step_3.index("These are not proof:"):]

    assert "`!`" in check and "pasted" in check
    assert "shown, not checked" in check
    assert "still ask the open question" in check and "their own words" in check
    assert "`!`" in not_proof and "shown, not checked" in not_proof


def test_the_tick_reminder_and_the_rule_block_say_the_same_about_output_in_the_chat():
    for text in (hooks.TICKED, one_line(rule_block())):
        assert "in their own words" in text
        assert "`!`" in text and "shown, not checked" in text


# ---------- finding 4: an older folder is asked everything in ONE message ----------

def test_an_old_ticket_with_milestones_gets_four_questions_in_one_message(tmp_path):
    settings, work = ticket(tmp_path, OLD)
    (work / ".git").mkdir()
    for message in (write(settings, work / "report.py"), begin(settings, work)[0]):
        assert "ONE message" in message and "one answer" in message
        for question in (CREATOR, BUT, NAME, APPROVE):
            assert question in message
        assert "price" in message                                # the price comes before every yes to a plan
        assert "second time" in message                          # the skills must not ask them again
        assert "already ticked stay ticked" in message
        assert "ticket-flow:clear-ticket" in message and "ticket-flow:plan-milestones" in message
        assert 'A no, or a "but", on 1:' in message and "clear-ticket skill takes it from there" in message


def test_an_old_ticket_without_milestones_gets_the_first_three_only(tmp_path):
    settings, work = ticket(tmp_path, OLD_NO_MILESTONES)
    (work / ".git").mkdir()
    for message in (write(settings, work / "report.py"), begin(settings, work)[0]):
        assert "ONE message" in message and "one answer" in message
        for question in (CREATOR, BUT, NAME):
            assert question in message
        assert "Do you approve" not in message and "second time" in message
        assert "ticket-flow:clear-ticket" in message


def test_clear_ticket_asks_an_old_ticket_the_same_questions_in_one_message():
    """Before: the hook said "both questions", the skill asked one, then two more in a row."""
    row = table_row(section(skill_text("clear-ticket"), "Step 0"), "Real content but no Status line")

    assert "Ask once, in ONE message" in row and "one answer" in row
    for question in (CREATOR, BUT, NAME, APPROVE):
        assert question in row
    assert "price" in row and "ticket-flow:plan-milestones" in row
    assert "do not ask any of them a second time" in row
    assert '`Asked about a "but":`' in row                       # the proof says the "but" was asked: it was
    assert "Step 8" in row and "CONFIRMED" in row


def test_plan_milestones_does_not_ask_an_old_ticket_for_its_approval_twice():
    row = table_row(section(skill_text("plan-milestones"), "Step 0"), "Milestone lines from before this skill")

    assert "ONE message" in row and "do not ask it a second time" in row
    assert row.index("price") < row.index(f'"{APPROVE}"')        # the price still comes first


# ---------- review round 1, 2026-11-20: the tests below failed before their fix ----------

def test_an_old_plan_is_not_approved_before_the_creators_yes(tmp_path):
    """A no or a "but" on the creator, with a yes on the milestones: the plan must not be approved.
    Else "Plan approved by" is in the file first, and code opens the moment the creator's yes arrives."""
    settings, work = ticket(tmp_path, OLD)
    (work / ".git").mkdir()
    for message in (write(settings, work / "report.py"), begin(settings, work)[0]):
        assert "Only then does a yes on 4 count" in message
        assert "the answer to 4 does not count" in message and "stay a draft" in message
        assert "A no on 4 only: the ticket-flow:plan-milestones skill takes it from there." in message

    clear = table_row(section(skill_text("clear-ticket"), "Step 0"), "Real content but no Status line")
    assert "the answer to question 4 does not count" in clear and "stay a draft" in clear

    plan = table_row(section(skill_text("plan-milestones"), "Step 0"), "Milestone lines from before this skill")
    assert "only in the same session" in plan and 'no "but"' in plan       # never an approval from an earlier day
    assert "Otherwise ask it here" in plan


@pytest.mark.parametrize("name", ["clear-ticket", "plan-milestones"])
def test_the_one_question_rule_makes_room_for_the_one_message(name):
    """Else Claude settles the clash by splitting the questions again: what finding 4 was about."""
    rules = one_line(section(skill_text(name), "Rules for the whole skill"))

    assert "Ask ONE question per message, then wait" in rules
    assert "unless a step says ONE message" in rules


def test_the_common_mistake_is_about_the_engineers_four_questions_only():
    mistakes = section(skill_text("clear-ticket"), "Common mistakes")

    assert "| Asking all four questions in one message |" not in mistakes     # Step 0 asks four in one, on purpose
    assert "Step 2" in table_row(mistakes, "Asking the four questions of Step 2 in one message")


# ---------- review round 2, 2026-11-20: the test below failed before its fix ----------

@pytest.mark.parametrize("reqs", [OLD, OLD_NO_MILESTONES])
def test_a_later_reply_from_the_creator_still_gets_its_own_but_question(tmp_path, reqs):
    """"Do not ask a second time" is about this one answer. After a no or a "but" the creator replies again,
    and the file may say "no but" for that reply only when it was asked for that reply."""
    settings, work = ticket(tmp_path, reqs)
    (work / ".git").mkdir()
    for message in (write(settings, work / "report.py"), begin(settings, work)[0]):
        assert "a second time for this answer" in message
        assert "A reply the creator sends later is a new reply" in message
        assert 'its own "but" question' in message and "Step 8" in message

    row = table_row(section(skill_text("clear-ticket"), "Step 0"), "Real content but no Status line")
    assert row.index('Yes and no "but":') < row.index("do not ask any of them a second time")   # on that path only
    assert "A reply the creator sends later is a new reply" in row
    assert 'Step 8 asks its "but" question again' in row


# ---------- review round 3, 2026-11-20 (the user chose to fix it): the test below failed before its fix ----------

@pytest.mark.parametrize("reqs", [OLD, OLD_NO_MILESTONES])
def test_a_question_the_engineer_left_out_is_asked_again(tmp_path, reqs):
    """"Yes, she confirmed, approve them" says nothing about a "but" or the name. "Do not ask a second time"
    must not stop Claude from asking those: else the file says "no but" although nobody answered that."""
    settings, work = ticket(tmp_path, reqs)
    (work / ".git").mkdir()
    for message in (write(settings, work / "report.py"), begin(settings, work)[0]):
        assert "Do not ask an answered question a second time" in message
        assert "A question the user left out is asked again, once" in message
        assert "before anything is written" in message

    row = table_row(section(skill_text("clear-ticket"), "Step 0"), "Real content but no Status line")
    assert "leaves a question out" in row and "ask that one again, once" in row
    assert "before anything is written" in row
    assert row.index("leaves a question out") < row.index('Yes and no "but":')      # asked before any path is taken

    plan = table_row(section(skill_text("plan-milestones"), "Step 0"), "Milestone lines from before this skill")
    assert "if the engineer gave one" in plan                    # no answer to question 4 = ask it here


# ---------- review round 4, 2026-11-20 (the user chose to fix it): the test below failed before its fix ----------

@pytest.mark.parametrize("reqs", [OLD, OLD_NO_MILESTONES])
def test_a_question_left_out_twice_means_nothing_is_written(tmp_path, reqs):
    """Asked again "once" said nothing about a second skip: Claude could write the proof without the name."""
    settings, work = ticket(tmp_path, reqs)
    (work / ".git").mkdir()
    for message in (write(settings, work / "report.py"), begin(settings, work)[0]):
        assert "Still not answered: write nothing" in message and "what is missing" in message

    row = table_row(section(skill_text("clear-ticket"), "Step 0"), "Real content but no Status line")
    assert "Still not answered after that: write nothing in the file" in row and "which answer is missing" in row
    assert row.index("Still not answered after that") < row.index('Yes and no "but":')
