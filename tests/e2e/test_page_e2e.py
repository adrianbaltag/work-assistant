"""The page in a real browser (Playwright): it opens, the main data shows, the main buttons work.

Skipped when Playwright is not installed (normal on the work laptop); it runs on the Mac.
Everything is made up: see conftest.py in this folder.
"""
import pytest

pytest.importorskip("pytest_playwright", reason="Playwright is not installed (normal on the work laptop)")

from playwright.sync_api import expect      # noqa: E402  (after the skip above, on purpose)

import dashboard_inbox                       # noqa: E402
import notes                                 # noqa: E402
import project_note as pn                    # noqa: E402
from conftest import LOG, LONG_ENTRY, LONG_NEXT, NOW   # noqa: E402


def row(page, project_id):
    return page.locator(f'button.prow[data-open="{project_id}"]')


def open_card(page, project_id):
    row(page, project_id).click()
    expect(page.locator("#ov")).to_be_visible()
    expect(page.locator("#f-title")).to_be_visible()


# ---------- the dashboard ----------

def test_the_dashboard_opens_and_shows_every_project(dash):
    expect(dash).to_have_title("Work Assistant")
    expect(row(dash, "DEMO-1")).to_contain_text("Demo one")
    # A step like "M8 of 9 · Email alerts" is drawn in two parts (number, name); the whole text is the hover title.
    expect(row(dash, "DEMO-1")).to_contain_text("M8 of 9")
    expect(row(dash, "DEMO-1")).to_contain_text("Email alerts")
    expect(row(dash, "DEMO-1").locator('[title="M8 of 9 · Email alerts"]')).to_be_visible()
    expect(row(dash, "DEMO-42")).to_contain_text("M2 — parse the alarm file")


def test_a_note_in_the_wrong_encoding_is_its_own_row_and_the_others_still_show(dash):
    expect(row(dash, "BAD-1")).to_contain_text("UTF-8")          # the row says how to fix that note
    expect(row(dash, "DEMO-1")).to_be_visible()
    expect(row(dash, "DEMO-42")).to_be_visible()


def test_a_card_follows_its_work_folder_after_a_change_by_hand(dash, folders):
    """No Claude session, no hook: the log is changed by hand and the next refresh of the page shows it."""
    projects, work_jira = folders
    (work_jira / "DEMO-42" / pn.TRACKING_LOG).write_text(
        LOG.format(now="M3 — email the report", last="2026-11-18 — M2 ticked"), encoding="utf-8")
    dash.reload()
    expect(row(dash, "DEMO-42")).to_contain_text("M3 — email the report")
    history = notes.read_history((projects / "DEMO-42" / notes.NOTE_FILE).read_text(encoding="utf-8"))
    assert history[0]["text"] == "M2 ticked" and history[0]["who"] == pn.WHO


# ---------- the card ----------

def test_the_box_sends_a_note_and_the_history_shows_it(dash, folders):
    """The Note button of the box at the top of the card (it took the place of "Add a line to the history")."""
    open_card(dash, "DEMO-1")
    dash.locator("#msg-text").fill("Senior said: Northeast markets only")
    dash.locator("#msg-note").click()
    first = dash.locator("#v-log li").first
    expect(first).to_contain_text("Senior said: Northeast markets only")
    expect(first).to_contain_text("you")
    expect(dash.locator("#msg-text")).to_have_value("")          # sent: the box is empty again
    expect(dash.locator("#msg-sent")).to_have_count(0)           # no Claude folder: no "waiting for Claude" list
    note = (folders[0] / "DEMO-1" / notes.NOTE_FILE).read_text(encoding="utf-8")
    assert "· you · Senior said: Northeast markets only" in note
    assert [p.name for p in (folders[0] / "DEMO-1").iterdir() if p.name.endswith(".tmp")] == []    # the save left nothing behind


def test_a_note_with_no_words_is_not_sent_and_says_so(dash, folders):
    open_card(dash, "DEMO-1")
    before = (folders[0] / "DEMO-1" / notes.NOTE_FILE).read_text(encoding="utf-8")
    dash.locator("#msg-note").click()
    expect(dash.locator("#msg-alert")).to_contain_text("Type a few words first")
    assert (folders[0] / "DEMO-1" / notes.NOTE_FILE).read_text(encoding="utf-8") == before


def test_a_sent_note_leaves_what_you_typed_in_the_fields(dash):
    open_card(dash, "DEMO-1")
    dash.locator("#f-jira").fill("TEST-7")                       # typed, not saved yet
    dash.locator("#msg-text").fill("Dana called")
    dash.locator("#msg-note").click()
    expect(dash.locator("#v-log li").first).to_contain_text("Dana called")
    expect(dash.locator("#f-jira")).to_have_value("TEST-7")


def test_a_changed_field_is_saved_with_save_changes(dash, folders):
    open_card(dash, "DEMO-1")
    dash.locator("#f-blocked_by").fill("waiting for the lab slot")
    with dash.expect_request("**/fields") as sent:
        dash.locator("#v-save").click()
    assert sent.value.post_data_json["fields"] == {"blocked_by": "waiting for the lab slot"}    # only the box that changed
    expect(dash.locator("#toast")).to_be_visible()
    fields = notes.parse_note((folders[0] / "DEMO-1" / notes.NOTE_FILE).read_text(encoding="utf-8"))[0]
    assert fields["blocked_by"] == "waiting for the lab slot"
    assert fields["next"] == LONG_NEXT                       # the long value went through the growing box unchanged


def test_save_with_nothing_changed_sends_nothing_and_says_so(dash, folders):
    open_card(dash, "DEMO-1")
    before = (folders[0] / "DEMO-1" / notes.NOTE_FILE).read_bytes()
    dash.locator("#v-save").click()
    expect(dash.locator("#toast")).to_contain_text("Nothing to save")
    assert (folders[0] / "DEMO-1" / notes.NOTE_FILE).read_bytes() == before


def test_the_save_button_is_in_view_without_scrolling(dash):
    dash.set_viewport_size({"width": 1366, "height": 620})       # a short laptop window: the card is taller than it
    open_card(dash, "DEMO-1")
    view = dash.locator("#m-view")
    sizes = view.evaluate("v => ({scroll: v.scrollHeight, client: v.clientHeight})")
    assert sizes["scroll"] > sizes["client"] + 50                # there IS more card than fits: the column scrolls
    expect(dash.locator("#v-save")).to_be_in_viewport(ratio=1)   # at the top of the card
    view.evaluate("v => { v.scrollTop = v.scrollHeight / 2; }")
    expect(dash.locator("#v-save")).to_be_in_viewport(ratio=1)   # half way down
    view.evaluate("v => { v.scrollTop = v.scrollHeight; }")
    expect(dash.locator("#v-save")).to_be_in_viewport(ratio=1)   # at the end
    box, column = dash.locator("#v-save").bounding_box(), view.bounding_box()
    assert box["y"] + box["height"] <= column["y"] + column["height"] + 1      # and inside the column, not under it


def test_a_long_history_line_is_cut_and_read_more_shows_all_of_it(dash):
    open_card(dash, "DEMO-1")
    line = dash.locator("#v-log li").first                   # the newest line is the long one
    more = line.locator("[data-more]")
    text = more.locator("xpath=preceding-sibling::span[1]")
    expect(more).to_have_text("Read more")
    expect(more).to_have_attribute("aria-expanded", "false")
    cut = text.inner_text()
    assert cut.endswith("…") and len(cut) <= 201 and LONG_ENTRY.startswith(cut[:-1])
    more.click()
    expect(text).to_have_text(LONG_ENTRY)
    expect(more).to_have_text("Show less")
    expect(more).to_have_attribute("aria-expanded", "true")
    more.click()
    expect(text).to_have_text(cut)
    expect(dash.locator("#v-log li").nth(1).locator("[data-more]")).to_have_count(0)     # a short line has no button


def test_a_long_next_step_shows_whole_in_a_box_that_grows(dash):
    open_card(dash, "DEMO-1")
    box, short = dash.locator("#f-next"), dash.locator("#f-working_on")
    sizes = box.evaluate("b => ({scroll: b.scrollHeight, client: b.clientHeight})")
    assert sizes["scroll"] <= sizes["client"] + 1            # nothing is hidden: all the text is on screen
    assert box.bounding_box()["height"] > short.bounding_box()["height"] * 1.5      # it wraps: taller than a one-line box
    assert abs(short.bounding_box()["height"] - dash.locator("#f-jira").bounding_box()["height"]) <= 0.5    # one line looks exactly like a plain box


def test_a_growing_box_stays_one_line_of_text(dash):
    open_card(dash, "DEMO-1")
    box = dash.locator("#f-blocked_by")
    box.fill("waiting for Dana")
    box.press("Enter")                                       # Enter adds no line break
    assert box.input_value() == "waiting for Dana"
    # Paste two lines into the middle, right after "waiting ": the text goes in as one line, the cursor right after it.
    box.evaluate("""b => {
        b.focus(); b.setSelectionRange(8, 8);
        const data = new DataTransfer(); data.setData("text", "one\\ntwo ");
        b.dispatchEvent(new ClipboardEvent("paste", {clipboardData: data, bubbles: true, cancelable: true}));
    }""")
    assert box.input_value() == "waiting one two for Dana"
    assert box.evaluate("b => b.selectionStart") == len("waiting one two ")


# ---------- two-way: Note / Blocker / Unblock from the dashboard to Claude ----------

WIDE = {"width": 1440, "height": 900}        # wide enough for the dashboard's "Blocked by" column


def plus(page, project_id):
    return page.locator(f'button.padd[data-add="{project_id}"]')


def close_card(page):
    page.locator("#m-close").click()
    expect(page.locator("#ov")).to_be_hidden()


def fields_of(folders, project_id):
    return notes.parse_note((folders[0] / project_id / notes.NOTE_FILE).read_text(encoding="utf-8"))[0]


def test_a_blocker_blocks_the_card_and_the_row_by_you_and_unblock_clears_it(dash, folders):
    dash.set_viewport_size(WIDE)
    expect(row(dash, "DEMO-1").locator(".pill").first).to_have_text("active")
    open_card(dash, "DEMO-1")
    expect(dash.locator("#msg-unblock")).to_be_hidden()          # Unblock shows only while your blocker is on
    dash.locator("#msg-text").fill("waiting for Dana")
    dash.locator("#msg-blocker").click()

    expect(dash.locator("#m-status")).to_have_text("pending")    # the card: blocked, by you
    expect(dash.locator("#msg-blocked")).to_contain_text("you")
    expect(dash.locator("#msg-blocked")).to_contain_text("waiting for Dana")
    expect(dash.locator("#msg-unblock")).to_be_visible()
    expect(dash.locator("#v-log li").first).to_contain_text("Blocker: waiting for Dana")
    assert fields_of(folders, "DEMO-1")["my_blocker"] == "waiting for Dana"
    assert fields_of(folders, "DEMO-1")["status"] == "active"    # the saved status is not touched

    close_card(dash)
    line = row(dash, "DEMO-1")                                   # the dashboard row: pending, "you" + the reason
    expect(line.locator(".pill").first).to_have_text("pending")
    expect(line.locator(".by")).to_have_text("you")
    expect(line).to_contain_text("waiting for Dana")

    open_card(dash, "DEMO-1")
    dash.locator("#msg-unblock").click()                         # no words needed
    expect(dash.locator("#m-status")).to_have_text("active")
    expect(dash.locator("#msg-unblock")).to_be_hidden()
    expect(dash.locator("#msg-text")).to_be_focused()            # the button is gone: the keyboard focus is not lost
    expect(dash.locator("#msg-blocked")).to_have_count(0)
    close_card(dash)
    expect(row(dash, "DEMO-1").locator(".pill").first).to_have_text("active")
    expect(row(dash, "DEMO-1").locator(".by")).to_have_count(0)
    assert fields_of(folders, "DEMO-1")["my_blocker"] == ""


def test_the_plus_on_a_row_opens_the_card_with_the_cursor_in_the_box(dash, folders):
    plus(dash, "DEMO-1").click()
    expect(dash.locator("#ov")).to_be_visible()
    expect(dash.locator("#m-title")).to_have_text("Demo one")
    expect(dash.locator("#msg-text")).to_be_focused()
    dash.keyboard.type("typed straight away")                    # no click needed: the cursor is in the box
    dash.keyboard.press("Tab")
    expect(dash.locator("#msg-note")).to_be_focused()
    dash.keyboard.press("Enter")
    expect(dash.locator("#v-log li").first).to_contain_text("typed straight away")


def test_the_row_and_its_plus_both_work_from_the_keyboard(dash):
    assert dash.locator("button button").count() == 0            # never a button inside a button
    expect(plus(dash, "BAD-1")).to_have_count(0)                 # a note that can't be read has no card to write in
    row(dash, "DEMO-1").focus()
    dash.keyboard.press("Tab")                                   # Tab goes from the row to its "+"
    expect(plus(dash, "DEMO-1")).to_be_focused()
    dash.keyboard.press("Enter")
    expect(dash.locator("#msg-text")).to_be_focused()
    dash.keyboard.press("Escape")
    expect(dash.locator("#ov")).to_be_hidden()
    row(dash, "DEMO-1").focus()
    dash.keyboard.press("Enter")                                 # Enter on the row still opens the card, as before
    expect(dash.locator("#ov")).to_be_visible()
    expect(dash.locator("#m-close")).to_be_focused()


def test_a_linked_card_shows_the_four_values_as_text_and_waiting_for_claude_after_a_send(dash, folders):
    open_card(dash, "DEMO-42")
    for key in ["status", "working_on", "next", "blocked_by"]:
        expect(dash.locator(f"#f-{key}")).to_have_count(0)       # not boxes
    expect(dash.locator("#v-synced")).to_contain_text("Filled in by Claude's files")
    expect(dash.locator("#s-status")).to_have_text("active")
    expect(dash.locator("#s-working_on")).to_have_text("M2 — parse the alarm file")
    expect(dash.locator("#s-next")).to_have_text("M3 — email the report")
    expect(dash.locator("#f-title")).to_be_visible()             # the name is still yours to change

    dash.locator("#msg-text").fill("Dana wants the csv by Friday")
    dash.locator("#msg-note").click()
    sent = dash.locator("#msg-sent li").first
    expect(sent).to_contain_text("Dana wants the csv by Friday")
    expect(sent).to_contain_text("waiting for Claude")
    expect(dash.locator("#v-log li").first).to_contain_text("Dana wants the csv by Friday")
    messages = dashboard_inbox.read_all(folders[1] / "DEMO-42")
    assert [(m["kind"], m["text"]) for m in messages] == [("note", "Dana wants the csv by Friday")]

    # A Claude Code hook hands the message to Claude: the card then says so, with the day.
    dashboard_inbox.mark_seen(folders[1] / "DEMO-42", [messages[0]["id"]], NOW)
    close_card(dash)
    open_card(dash, "DEMO-42")
    expect(dash.locator("#msg-sent li").first).to_contain_text("seen by Claude 2026-11-18")


def test_a_card_opens_at_its_top_not_where_the_last_card_was_left(dash):
    dash.set_viewport_size({"width": 1366, "height": 620})
    open_card(dash, "DEMO-1")
    dash.locator("#m-view").evaluate("v => { v.scrollTop = v.scrollHeight; }")
    close_card(dash)
    open_card(dash, "DEMO-42")
    expect(dash.locator("#msg-text")).to_be_in_viewport()
    assert dash.locator("#m-view").evaluate("v => v.scrollTop") == 0


def test_after_a_note_save_changes_still_works_without_a_false_warning(dash, folders):
    open_card(dash, "DEMO-1")
    dash.locator("#msg-text").fill("Dana called")
    dash.locator("#msg-note").click()
    expect(dash.locator("#v-log li").first).to_contain_text("Dana called")
    dash.locator("#f-jira").fill("TEST-7")
    dash.locator("#v-save").click()
    expect(dash.locator("#toast")).to_have_text("Saved")
    expect(dash.locator("#v-reload")).to_have_count(0)           # no "this note changed" warning: the note was ours
    note = (folders[0] / "DEMO-1" / notes.NOTE_FILE).read_text(encoding="utf-8")
    assert "jira: TEST-7" in note and "· you · Dana called" in note


def test_a_note_does_not_hide_that_someone_else_changed_the_card(dash, folders):
    """The note goes in without a warning, but Save changes must still say that the note changed under you."""
    open_card(dash, "DEMO-1")
    note = folders[0] / "DEMO-1" / notes.NOTE_FILE
    note.write_text(note.read_text(encoding="utf-8").replace("## Goal", "## Goal\nwritten by someone else"), encoding="utf-8")
    dash.locator("#msg-text").fill("Dana called")
    dash.locator("#msg-note").click()
    expect(dash.locator("#v-log li").first).to_contain_text("Dana called")     # no warning for the note itself
    expect(dash.locator("#msg-alert")).to_be_empty()
    dash.locator("#f-jira").fill("TEST-7")
    dash.locator("#v-save").click()
    expect(dash.locator("#v-reload")).to_be_visible()            # the usual choice: load theirs, or save mine anyway
    text = note.read_text(encoding="utf-8")
    assert "written by someone else" in text and "· you · Dana called" in text and "TEST-7" not in text


def test_an_unlinked_card_keeps_its_boxes(dash):
    open_card(dash, "DEMO-1")
    for key in ["status", "working_on", "next", "blocked_by"]:
        expect(dash.locator(f"#f-{key}")).to_be_visible()
    expect(dash.locator("#v-synced")).to_have_count(0)


def test_save_on_a_linked_card_keeps_the_synced_values_and_the_unsent_message(dash, folders):
    before = fields_of(folders, "DEMO-42")
    open_card(dash, "DEMO-42")
    dash.locator("#msg-text").fill("half typed, not sent")
    dash.locator("#f-title").fill("Alarm parser")
    with dash.expect_request("**/fields") as sent:
        dash.locator("#v-save").click()
    assert sent.value.post_data_json["fields"] == {"title": "Alarm parser"}
    expect(dash.locator("#m-title")).to_have_text("Alarm parser")
    expect(dash.locator("#msg-text")).to_have_value("half typed, not sent")      # Save did not throw it away
    after = fields_of(folders, "DEMO-42")
    assert after["title"] == "Alarm parser"
    for key in notes.SYNCED_FIELDS:
        assert after.get(key, "") == before.get(key, ""), key
    expect(dash.locator("#s-working_on")).to_have_text("M2 — parse the alarm file")


def test_your_blocker_and_the_logs_blocker_both_show_with_their_labels(dash, folders):
    dash.set_viewport_size(WIDE)
    (folders[1] / "DEMO-42" / pn.TRACKING_LOG).write_text(
        LOG.format(now="PENDING (Dana, 2026-11-17): waiting for the lab key. M2 — parse the alarm file",
                   last="2026-11-17 — M1 ticked"), encoding="utf-8")
    dash.reload()
    expect(row(dash, "DEMO-42").locator(".by")).to_have_text(["log"])
    plus(dash, "DEMO-42").click()
    dash.locator("#msg-text").fill("waiting for Dana")
    dash.locator("#msg-blocker").click()
    expect(dash.locator("#msg-blocked .by")).to_have_text(["you", "log"])
    expect(dash.locator("#s-status")).to_have_text("pending")    # what the log says, as plain text
    close_card(dash)
    line = row(dash, "DEMO-42")
    expect(line.locator(".by")).to_have_text(["you", "log"])
    expect(line).to_contain_text("waiting for Dana")
    expect(line).to_contain_text("waiting for the lab key.")
    open_card(dash, "DEMO-42")
    dash.locator("#msg-unblock").click()                         # yours is gone, the log's is not: still pending
    expect(dash.locator("#msg-blocked .by")).to_have_text(["log"])
    expect(dash.locator("#m-status")).to_have_text("pending")


def test_work_folder_away_the_card_says_not_sent_and_keeps_your_words(dash, folders):
    open_card(dash, "DEMO-42")
    (folders[1] / "DEMO-42").rename(folders[1] / "DEMO-42-moved")
    dash.locator("#msg-text").fill("Dana wants the csv by Friday")
    dash.locator("#msg-note").click()
    expect(dash.locator("#msg-alert")).to_contain_text("Not sent")
    expect(dash.locator("#msg-alert")).to_contain_text("Nothing was changed")
    expect(dash.locator("#msg-text")).to_have_value("Dana wants the csv by Friday")
    assert "Dana wants the csv" not in (folders[0] / "DEMO-42" / notes.NOTE_FILE).read_text(encoding="utf-8")


def test_the_hint_under_the_box_says_when_claude_gets_the_message(dash):
    open_card(dash, "DEMO-42")                                   # follows a Claude folder
    expect(dash.locator("#msg .hint")).to_have_text(
        "Goes into the History, and Claude gets it the next time you write to it.")
    close_card(dash)
    open_card(dash, "DEMO-1")                                    # a personal card: nobody to hand it to
    expect(dash.locator("#msg .hint")).to_have_text("Goes into the History.")
