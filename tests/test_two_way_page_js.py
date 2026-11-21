"""Two-way, the page's own small rules (static/paging.js run in Node, and what the page scripts must hold).

The Node tests skip when Node is not installed (normal on the work laptop); they run on the Mac.
What the page does in a real browser is in tests/e2e/test_page_e2e.py.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).parent.parent / "static"
PAGING_JS = STATIC / "paging.js"
NO_FILTER = {"q": "", "status": "", "prio": ""}


@pytest.fixture
def js():
    """js("changedFields", {...}, {...}) = call that function from paging.js in Node and get its answer back."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed (normal on the work laptop)")

    def run(name, *args):
        call = f"{name}({', '.join(json.dumps(a) for a in args)})"
        script = f"const p = require({json.dumps(str(PAGING_JS))}); console.log(JSON.stringify(p.{call}));"
        done = subprocess.run([node, "-e", script], capture_output=True, encoding="utf-8", timeout=30)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)
    return run


def project(**fields):
    return {"id": "A", "title": "Demo", "status": "active", "shown_status": "active", "priority": "normal", **fields}


# ---------- the dashboard filters see what the dashboard shows ----------

def test_the_status_filter_uses_the_shown_status(js):
    blocked_by_you = project(shown_status="pending", my_blocker="waiting for Dana")
    assert js("filterProjects", [blocked_by_you], {**NO_FILTER, "status": "pending"}) == [blocked_by_you]
    assert js("filterProjects", [blocked_by_you], {**NO_FILTER, "status": "active"}) == []


def test_the_search_box_finds_your_own_blocker(js):
    rows = [project(id="A", my_blocker="waiting for Dana"), project(id="B")]
    assert [p["id"] for p in js("filterProjects", rows, {**NO_FILTER, "q": "dana"})] == ["A"]


# ---------- Save sends only the boxes you changed ----------

@pytest.mark.parametrize("drawn, now, changed", [
    ({"title": "Demo", "jira": ""}, {"title": "Demo", "jira": ""}, {}),
    ({"title": "Demo", "jira": ""}, {"title": "Demo", "jira": "TEST-7"}, {"jira": "TEST-7"}),
    ({"title": "Demo", "next": "x"}, {"title": "New", "next": ""}, {"title": "New", "next": ""}),   # emptied = a change
    ({"title": "Demo"}, {"title": "Demo", "status": "idea"}, {"status": "idea"}),                   # a box that was not there before
])
def test_changed_fields_are_the_boxes_that_differ_from_what_was_drawn(js, drawn, now, changed):
    assert js("changedFields", drawn, now) == changed


# ---------- what the scripts must hold ----------

def text_of(name):
    return (STATIC / name).read_text(encoding="utf-8")


def test_the_old_history_control_is_gone_and_the_message_box_is_there():
    card = text_of("card.js")
    assert "v-addline" not in card and "f-line" not in card
    for wanted in ['id="msg-text"', 'id="msg-note"', 'id="msg-blocker"', 'id="msg-unblock"']:
        assert wanted in card, wanted
    assert 'post("message"' in card or 'act("message"' in card


def test_save_sends_only_changed_fields_and_never_a_synced_one_on_a_linked_card():
    card = text_of("card.js")
    assert "changedFields(" in card
    assert "Filled in by Claude's files" in card


def test_a_row_is_a_button_with_a_sibling_row_end_never_a_button_inside_a_button():
    """The HTML app.js builds for one list line: the row end ("✓ Complete") comes after the row button has closed."""
    app = text_of("app.js")
    line = app[app.index('<div class="prow-wrap"'):]
    line = line[:line.index("</div>`")]
    assert line.index("</button>") < line.index("${rowEnd(p)}")       # the row button closes first
    assert len(re.findall(r"<button\b", line)) == 1 and len(re.findall(r"</button>", line)) == 1
    done = text_of("completed.js")
    end = done[done.index("function rowEnd"):done.index("// One row on the Completed tab")]
    assert len(re.findall(r"<button\b", end)) == len(re.findall(r"</button>", end)) == 1   # one whole button


def test_every_new_colour_is_a_token_from_root():
    """ui-standards: no raw colour outside :root in the rules this feature added."""
    css = text_of("app.css")
    added = css[css.index("/* Two-way:"):css.index("/* end Two-way */")]
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b|rgba?\(|hsla?\(", added), "use a var(--token) from :root"
