"""The Ideas page in a real browser (Playwright): add, delete, the (i) note, Start as project.

Skipped when Playwright is not installed (normal on the work laptop); it runs on the Mac.
Everything is made up: see conftest.py in this folder.
"""
import pytest

pytest.importorskip("pytest_playwright", reason="Playwright is not installed (normal on the work laptop)")

from playwright.sync_api import expect      # noqa: E402  (after the skip above, on purpose)

import ideas                                 # noqa: E402

FILE = "# Ideas\n\n## 2026-11-21 · Rename old scripts\nThey all start with tmp_.\nPick one style.\n\n## 2026-11-20 · A quick one\n"


@pytest.fixture
def idea_page(dash, folders):
    """The Ideas page with two made-up ideas, opened from the sidebar."""
    (folders[0] / ideas.IDEA_FILE).write_text(FILE, encoding="utf-8")
    dash.locator('.nav[data-page="ideas"]').click()
    expect(dash.locator("#page-ideas")).to_be_visible()
    return dash


def names(page):
    return page.locator("#idea-list .iname")


def test_the_ideas_page_shows_each_idea_newest_first_with_details_and_date(idea_page):
    expect(names(idea_page)).to_have_text(["Rename old scripts", "A quick one"])
    first = idea_page.locator("#idea-list .irow").first
    expect(first).to_contain_text("They all start with tmp_.")
    expect(first).to_contain_text("2026-11-21")
    expect(idea_page.locator("#ideas-summary")).to_have_text("2 ideas")


def test_enter_saves_shift_enter_makes_a_new_line_and_the_box_grows(idea_page, folders):
    box = idea_page.locator("#idea-new")
    one_line = box.bounding_box()["height"]
    box.click()
    box.type("Cache the alarm list")
    box.press("Shift+Enter")
    box.type("Saves a minute each run")
    assert box.bounding_box()["height"] > one_line          # grew to two lines, nothing saved yet
    assert ideas.read_ideas(folders[0])[0]["name"] == "Rename old scripts"
    box.press("Enter")
    expect(names(idea_page).first).to_have_text("Cache the alarm list")
    expect(box).to_have_value("")
    saved = ideas.read_ideas(folders[0])[0]
    assert (saved["name"], saved["details"]) == ("Cache the alarm list", "Saves a minute each run")


def test_the_info_icon_says_how_to_change_an_idea(idea_page):
    info = idea_page.locator("#idea-info")
    expect(idea_page.locator("#idea-help")).to_be_hidden()
    info.click()
    expect(idea_page.locator("#idea-help")).to_have_text("To change an idea, delete it and add it again.")
    expect(info).to_have_attribute("aria-expanded", "true")
    info.click()
    expect(idea_page.locator("#idea-help")).to_be_hidden()


def test_delete_asks_for_good_and_cancel_keeps_it(idea_page, folders):
    idea_page.locator('#idea-list .irow').first.locator('[data-act="delete"]').click()
    expect(idea_page.locator("#idea-list .tconfirm")).to_contain_text("Delete this idea for good?")
    idea_page.locator('[data-act="delete-no"]').click()
    expect(names(idea_page)).to_have_count(2)
    idea_page.locator('#idea-list .irow').first.locator('[data-act="delete"]').click()
    idea_page.locator('[data-act="delete-yes"]').click()
    expect(names(idea_page)).to_have_text(["A quick one"])
    assert [i["name"] for i in ideas.read_ideas(folders[0])] == ["A quick one"]


def test_start_as_project_fills_the_form_makes_the_card_and_removes_the_idea(idea_page, folders):
    idea_page.locator('#idea-list .irow').first.locator('[data-act="start"]').click()
    expect(idea_page.locator("#np")).to_be_visible()
    expect(idea_page.locator("#np-title")).to_have_value("Rename old scripts")
    expect(idea_page.locator("#np-desc")).to_have_value("They all start with tmp_.\nPick one style.")
    expect(idea_page.locator("#np-id")).to_be_focused()
    idea_page.locator("#np-id").fill("ABC-777")
    idea_page.locator("#np-create").click()
    expect(idea_page.locator("#ov")).to_be_visible()                        # the new card opens
    expect(idea_page.locator("#f-title")).to_have_value("Rename old scripts")
    note = (folders[0] / "ABC-777" / "note.md").read_text(encoding="utf-8")
    assert "## Goal\nThey all start with tmp_.\nPick one style.\n" in note
    idea_page.keyboard.press("Escape")
    expect(names(idea_page)).to_have_text(["A quick one"])


def test_plus_new_project_after_start_as_project_is_empty_again(idea_page, folders):
    idea_page.locator('#idea-list .irow').first.locator('[data-act="start"]').click()
    idea_page.locator("#np-cancel").click()
    idea_page.locator('.nav[data-page="dash"]').click()
    idea_page.locator("#new-project").click()
    expect(idea_page.locator("#np-title")).to_have_value("")
    expect(idea_page.locator("#np-desc")).to_have_value("")
    idea_page.locator("#np-id").fill("plain_one")
    idea_page.locator("#np-create").click()
    expect(idea_page.locator("#ov")).to_be_visible()
    assert len(ideas.read_ideas(folders[0])) == 2           # a plain + New project never touches the ideas


def test_no_ideas_shows_a_friendly_empty_box(dash):
    dash.locator('.nav[data-page="ideas"]').click()
    expect(dash.locator("#idea-list .tempty")).to_contain_text("No ideas yet")
