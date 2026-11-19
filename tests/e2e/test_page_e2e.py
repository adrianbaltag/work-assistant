"""The page in a real browser (Playwright): it opens, the main data shows, the main buttons work.

Skipped when Playwright is not installed (normal on the work laptop); it runs on the Mac.
Everything is made up: see conftest.py in this folder.
"""
import pytest

pytest.importorskip("pytest_playwright", reason="Playwright is not installed (normal on the work laptop)")

from playwright.sync_api import expect      # noqa: E402  (after the skip above, on purpose)

import notes                                 # noqa: E402
import project_note as pn                    # noqa: E402
from conftest import LOG, LONG_ENTRY, LONG_NEXT   # noqa: E402


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

def test_a_history_line_can_be_added_and_is_saved_in_the_note(dash, folders):
    open_card(dash, "DEMO-1")
    dash.locator("#f-line").fill("Senior said: Northeast markets only")
    dash.locator("#v-addline").click()
    first = dash.locator("#v-log li").first
    expect(first).to_contain_text("Senior said: Northeast markets only")
    expect(first).to_contain_text("you")
    note = (folders[0] / "DEMO-1" / notes.NOTE_FILE).read_text(encoding="utf-8")
    assert "· you · Senior said: Northeast markets only" in note
    assert [p.name for p in (folders[0] / "DEMO-1").iterdir() if p.name.endswith(".tmp")] == []    # the save left nothing behind


def test_a_changed_field_is_saved_with_save_changes(dash, folders):
    open_card(dash, "DEMO-1")
    dash.locator("#f-blocked_by").fill("waiting for the lab slot")
    dash.locator("#v-save").click()
    expect(dash.locator("#toast")).to_be_visible()
    fields = notes.parse_note((folders[0] / "DEMO-1" / notes.NOTE_FILE).read_text(encoding="utf-8"))[0]
    assert fields["blocked_by"] == "waiting for the lab slot"
    assert fields["next"] == LONG_NEXT                       # the long value went through the growing box unchanged


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
    assert abs(short.bounding_box()["height"] - dash.locator("#f-jira").bounding_box()["height"]) <= 2    # one line looks like a plain box


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
