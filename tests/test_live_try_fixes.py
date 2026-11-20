"""Tests for what the second live try (2026-11-19, a made-up ticket through the real plugin) showed.

- A log entry that Claude extends with a comma (or ; : .) keeps ONE History line, and a line that got
  shorter in the log gets shorter on the card.
- One dashboard message = one History line, the user's: Claude's "Dashboard note: ..." log line is not
  copied to the card.
- The user's answer to "stop, or work around it?" is written in the log, and the next session follows it.

All folders are fake (tmp_path), all IDs and names are made up, nothing touches the network.
"""
from pathlib import Path

import pytest

import dashboard_inbox as inbox
import notes
import project_note as pn
import work_jira_hooks as hooks
from test_project_note import history_of, projects, work_project
from test_review_fixes import claude_lines, log_text, write_log
from test_ticket_flow import between, section, skill_text, table_row
from test_two_way_hooks import BLOCKER, NOTE, TODAY, ask, rule_block, send, write_in_log
from test_work_jira_hooks import NOW, begin, ticket

DAY = "2026-10-22"
REPO = Path(__file__).parent.parent


def synced_card(tmp_path, last):
    """A work folder whose log has this text under ## Last update, and its card after one sync."""
    work = work_project(tmp_path, log=log_text(last))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    pn.sync(projects(tmp_path), work, NOW)
    return work, card


def sync(tmp_path, work):
    pn.sync(projects(tmp_path), work, NOW)


# ---------- a log entry that grows after a comma, a semicolon, a colon or a full stop ----------

@pytest.mark.parametrize("mark", [",", ";", ":", "."])
def test_an_entry_that_grows_after_a_punctuation_mark_keeps_one_history_line(tmp_path, mark):
    work, card = synced_card(tmp_path, f"{DAY} — M2 ticked")
    write_log(work, f"{DAY} — M2 ticked{mark} 19 tests green")
    sync(tmp_path, work)
    assert claude_lines(card) == [f"M2 ticked{mark} 19 tests green"]
    sync(tmp_path, work)                                             # and never twice
    assert claude_lines(card) == [f"M2 ticked{mark} 19 tests green"]


def test_an_entry_that_gets_shorter_in_the_log_gets_shorter_on_the_card(tmp_path):
    work, card = synced_card(tmp_path, f"{DAY} — M2 ticked, 19 tests green")
    write_log(work, f"{DAY} — M2 ticked")
    sync(tmp_path, work)
    assert claude_lines(card) == ["M2 ticked"]


def test_a_shorter_word_is_not_a_shrunk_entry(tmp_path):
    work, card = synced_card(tmp_path, f"{DAY} — M20 ticked")
    write_log(work, f"{DAY} — M2")
    sync(tmp_path, work)
    assert sorted(claude_lines(card)) == ["M2", "M20 ticked"]


def test_two_entries_in_the_log_where_one_starts_like_the_other_stay_two_lines(tmp_path):
    work, card = synced_card(tmp_path, f"{DAY} — M2 ticked")
    write_log(work, f"{DAY} — M2 ticked\n{DAY} — M2 ticked, again after the review fix")
    sync(tmp_path, work)
    assert sorted(claude_lines(card)) == ["M2 ticked", "M2 ticked, again after the review fix"]
    sync(tmp_path, work)
    assert sorted(claude_lines(card)) == ["M2 ticked", "M2 ticked, again after the review fix"]


def test_the_longer_entry_first_and_the_shorter_one_added_stay_two_lines(tmp_path):
    work, card = synced_card(tmp_path, f"{DAY} — M2 ticked, again after the review fix")
    write_log(work, f"{DAY} — M2 ticked, again after the review fix\n{DAY} — M2 ticked")
    sync(tmp_path, work)
    assert sorted(claude_lines(card)) == ["M2 ticked", "M2 ticked, again after the review fix"]


def test_a_changed_entry_never_touches_another_day_or_a_line_you_typed(tmp_path):
    work = work_project(tmp_path, log=log_text(f"{DAY} — M2 ticked"))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    note = card / "note.md"
    text = notes.add_history(note.read_text(encoding="utf-8"), "M2 ticked, by hand", DAY, who="you")
    text = notes.add_history(text, "M2 ticked, the day before", "2026-10-21", who=pn.WHO)
    note.write_text(text, encoding="utf-8")
    sync(tmp_path, work)                                             # shorter than both: neither is replaced
    write_log(work, f"{DAY} — M2 ticked, by hand, and more")
    sync(tmp_path, work)                                             # longer than your line: yours stays
    lines = [(h["date"], h["who"], h["text"]) for h in history_of(card)]
    assert (DAY, "you", "M2 ticked, by hand") in lines
    assert ("2026-10-21", pn.WHO, "M2 ticked, the day before") in lines
    assert (DAY, pn.WHO, "M2 ticked, by hand, and more") in lines


# ---------- one dashboard message = one History line, the user's ----------

def echo_line(kind, text=""):
    """The log line the hooks tell Claude to write for a dashboard message of this kind."""
    return hooks.LOG_ENTRY[kind].format(today=DAY).replace("<text>", text)


@pytest.mark.parametrize("kind, text", [("note", NOTE), ("blocker", BLOCKER), ("unblock", "")])
def test_claudes_log_line_for_a_dashboard_message_is_not_copied_to_the_card(tmp_path, kind, text):
    work, card = synced_card(tmp_path, f"{DAY} — M1 ticked")
    write_log(work, f"{DAY} — M1 ticked\n{echo_line(kind, text)}")
    sync(tmp_path, work)
    assert claude_lines(card) == ["M1 ticked"]


def test_the_whole_line_stays_off_the_card_also_with_claudes_own_words_on_it(tmp_path):
    _, card = synced_card(tmp_path, f"{echo_line('note', NOTE)}. I will do it in M3\nand tell Dana on Monday")
    assert claude_lines(card) == []


def test_claudes_own_dated_line_next_to_it_still_reaches_the_card(tmp_path):
    _, card = synced_card(tmp_path, f"{echo_line('note', NOTE)}\n{DAY} — Moved the csv export into M3")
    assert claude_lines(card) == ["Moved the csv export into M3"]


@pytest.mark.parametrize("said", ["Answered the Dashboard note: Friday is fine",
                                  "Dashboard unblocked the export page", "Dashboard notes are now sorted by day"])
def test_a_line_that_only_looks_like_a_dashboard_message_is_copied(tmp_path, said):
    _, card = synced_card(tmp_path, f"{DAY} — {said}")
    assert claude_lines(card) == [said]


@pytest.mark.parametrize("said", ["dashboard NOTE: Dana wants the csv by Friday", "DASHBOARD BLOCKER: no lab key",
                                  "DASHBOARD UNBLOCK", "dashboard unblock."])
def test_claudes_copy_in_other_capitals_stays_off_the_card_too(tmp_path, said):
    assert inbox.is_echo(said)
    _, card = synced_card(tmp_path, f"{DAY} — M1 ticked\n{DAY} — {said}")
    assert claude_lines(card) == ["M1 ticked"]


def test_a_dashboard_line_already_on_the_card_stays_as_it_is(tmp_path):
    """Cards synced before this change have Claude's copy in the History: it is kept, and never doubled."""
    work = work_project(tmp_path, log=log_text(echo_line("note", NOTE)))
    card = notes.new_project(projects(tmp_path), "DEMO-42")
    note = card / "note.md"
    note.write_text(notes.add_history(note.read_text(encoding="utf-8"), f"Dashboard note: {NOTE}", DAY, who=pn.WHO),
                    encoding="utf-8")
    sync(tmp_path, work)
    assert claude_lines(card) == [f"Dashboard note: {NOTE}"]


def test_the_sync_and_the_hooks_share_the_words_of_the_log_line():
    for kind in inbox.KINDS:
        assert hooks.LOG_ENTRY[kind].startswith("{today} — " + inbox.LOG_WORDS[kind])
        assert inbox.is_echo(echo_line(kind, "any words").split(" — ", 1)[1])
    assert not inbox.is_echo("M2 ticked") and not inbox.is_echo("")


def test_claude_is_told_the_line_holds_only_the_users_words(tmp_path):
    settings, work = ticket(tmp_path)
    send(work)
    said = ask(work)
    assert "only the user's words" in said and "its own dated line" in said
    for template in (hooks.WRITE_NOW, hooks.WRITE_LATER, hooks.NOT_LOGGED):
        assert "only the user's words" in template and "its own dated line" in template


def test_the_rule_block_says_the_line_holds_only_the_users_words():
    rules = " ".join(rule_block().split())
    assert "only the user's words" in rules and "its own dated line" in rules


# ---------- the user's answer to "stop, or work around it?" is written down and followed ----------

def test_claude_is_told_to_write_the_users_answer_to_a_blocker_into_the_log(tmp_path):
    settings, work = ticket(tmp_path)
    send(work, "blocker", BLOCKER)
    said = ask(work)
    assert 'ask ONCE: "stop, or work on what the blocker does not touch?"' in said
    assert f"`{TODAY} — Blocker answer: stop`" in said and f"`{TODAY} — Blocker answer: work on <what>`" in said
    assert "the next session follows it" in said


def test_a_standing_blocker_with_an_answer_in_the_log_is_followed_and_not_asked_again(tmp_path):
    settings, work = ticket(tmp_path)
    send(work, "blocker", BLOCKER)
    begin(settings, work)
    write_in_log(work, f"{TODAY} — Dashboard blocker: {BLOCKER}")
    standing, _ = begin(settings, work)
    assert "Standing fact, not a new message" in standing
    assert "already holds the user's answer" in standing and "`Blocker answer:` line" in standing
    assert "follow that answer and do not ask again" in standing and "ONE line" in standing
    assert "Your blocker is still on. You said:" in standing
    assert "until the user says otherwise or sends an Unblock" in standing
    assert "No answer there yet" in standing and "ask once" in standing
    assert f"`{TODAY} — Blocker answer: stop`" in standing


def test_the_blocker_answer_line_reaches_the_card_as_claudes_line(tmp_path):
    _, card = synced_card(tmp_path, f"{echo_line('blocker', BLOCKER)}\n{DAY} — Blocker answer: work on the report page")
    assert claude_lines(card) == ["Blocker answer: work on the report page"]


def test_the_rule_block_has_the_blocker_answer_line():
    rules = " ".join(rule_block().split())
    assert "`YYYY-MM-DD — Blocker answer: stop`" in rules and "`YYYY-MM-DD — Blocker answer: work on <what>`" in rules
    assert "does not ask again" in rules


# ---------- wording: the page hint, and the three skills ----------

def test_the_hint_says_claude_gets_it_with_your_next_message():
    card_js = (REPO / "static" / "card.js").read_text(encoding="utf-8")
    assert "Goes into the History, and Claude gets it the next time you write to it." in card_js
    assert "in its next session" not in card_js


def test_clear_ticket_asks_real_questions_only_where_a_wrong_guess_costs():
    step_4 = section(skill_text("clear-ticket"), "Step 4")
    assert "does harm or changes what is built" in step_4
    assert '"I will assume these unless you say no:"' in step_4
    assert "the creator and the senior colleague" in step_4                  # both get the two kinds
    call = between(step_4, "more than about seven", "\n")
    assert "real questions" in call                                         # the assume list does not count


def test_clear_ticket_no_longer_says_every_guess_is_a_question():
    clear = skill_text("clear-ticket")
    assert "Both must turn into a question" not in clear
    assert "It becomes a question" not in table_row(clear, "Treating a Guess as settled")
    assert "assume list" in table_row(clear, "Treating a Guess as settled")
    assert "real question or on an assume list" in section(clear, "Step 4")  # the check before going on


def test_an_assumption_has_a_place_in_the_file_and_a_label_once_left_alone():
    clear = skill_text("clear-ticket")
    step_5 = between(clear, "## Step 5", "## Step 6")           # not section(): the layout has `## ` lines of its own
    assert "## Assumed unless someone says no" in step_5
    assert "<N> counts the real questions only" in step_5                    # the card's waiting line
    assert "`[Known] <fact> (assumed, <name> did not object, <date>)`" in between(clear, "## Step 6", "## Step 7")
    assert "assumed" in between(clear, "## Step 7", "## Step 8")                            # the creator's yes covers them too


def test_the_plan_is_shown_as_short_bullets_before_the_yes():
    step_7 = section(skill_text("plan-milestones"), "Step 7")
    assert "one bullet per milestone" in step_7 and "No test names in chat" in step_7
    assert "`- M2: build the tidy script. Proof: 19 tests (names in PLAN.md).`" in step_7
    assert "stay full" in step_7                                             # PLAN.md and requirements.md keep it all
    assert (step_7.index("one bullet per milestone") < step_7.index("sessions, <R> reviews")
            < step_7.index('"Do you approve this plan?"'))


def test_a_new_session_can_also_be_a_clear():
    for name in ("clear-ticket", "plan-milestones", "build-milestone"):
        assert "new session (or `/clear`)" in skill_text(name)
    assert "(or `/clear`)" in hooks.FINISHED and "(or `/clear`)" in hooks.LOCKED_CAN
