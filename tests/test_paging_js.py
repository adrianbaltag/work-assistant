"""The dashboard's paging maths (static/paging.js), run in Node.

These skip when Node is not installed (normal on the work laptop); they run on the Mac.
The browser runs the same file, so what passes here works in Edge/Chrome too.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).parent.parent / "static"
PAGING_JS = STATIC / "paging.js"


@pytest.fixture
def js():
    """js("pageList", 12, 6) = call that function from paging.js in Node and get its answer back."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed (normal on the work laptop)")

    def run(name, *args):
        call = f"{name}({', '.join(json.dumps(a) for a in args)})"
        script = f"const p = require({json.dumps(str(PAGING_JS))}); console.log(JSON.stringify(p.{call}));"
        done = subprocess.run([node, "-e", script], capture_output=True, encoding="utf-8", timeout=30)
        # encoding: Node prints UTF-8 ("…", "·"); Windows would read it as cp1252 without this.
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)
    return run


def test_the_page_loads_paging_js_before_app_js():
    page = (STATIC.parent / "templates" / "index.html").read_text(encoding="utf-8")
    assert "filename='paging.js'" in page
    assert page.index("filename='paging.js'") < page.index("filename='app.js'")


# ---------- page buttons ----------

@pytest.mark.parametrize("pages, current, buttons", [
    (1, 1, [1]),
    (7, 4, [1, 2, 3, 4, 5, 6, 7]),                        # up to 7 pages: all of them
    (12, 1, [1, 2, 3, 4, 5, "…", 12]),
    (12, 6, [1, "…", 5, 6, 7, "…", 12]),
    (12, 12, [1, "…", 8, 9, 10, 11, 12]),
    (8, 5, [1, "…", 4, 5, 6, 7, 8]),                       # no "…" standing for just one page
])
def test_page_buttons(js, pages, current, buttons):
    assert js("pageList", pages, current) == buttons


# ---------- how many rows fit ----------

@pytest.mark.parametrize("room, row_h, rows", [
    (460, 46, 10),
    (459, 46, 9),        # a row that does not fully fit is left out
    (50, 46, 3),         # very short window: still 3 rows (the page scrolls a little)
    (-20, 46, 3),
    (460, None, 3),      # the row height could not be read from app.css: 3 rows, not a broken page
])
def test_rows_that_fit(js, room, row_h, rows):
    assert js("rowsThatFit", room, row_h) == rows


@pytest.mark.parametrize("first, per_page, page", [
    (0, 5, 1),
    (8, 4, 3),     # rows 9-12 shown, then the window grows to 5 rows: page 2 = rows 6-10 holds row 9
    (8, 5, 2),
    (8, 9, 1),
])
def test_resize_keeps_the_top_row_on_screen(js, first, per_page, page):
    assert js("pageHolding", first, per_page) == page


# ---------- footer ----------

def test_footer_counts_projects(js):
    assert js("footerText", 0, 4, 20, 20, False) == "<b>1–4</b> of 20 projects"
    assert js("footerText", 4, 1, 5, 5, False) == "<b>5</b> of 5 projects"
    assert js("footerText", 0, 1, 1, 1, False) == "<b>1</b> of 1 project"


def test_footer_says_filtered_only_when_filters_are_set(js):
    assert js("footerText", 0, 4, 6, 20, True) == "<b>1–4</b> of 6 · filtered from 20"


# ---------- search box + dropdowns ----------

PROJECTS = [
    {"id": "A", "title": "Radio upgrade", "jira": "DEMO-1", "status": "active", "priority": "critical",
     "working_on": "M2 of 5 · test plan", "next": None, "blocked_by": ""},
    {"id": "B", "title": "Report tool", "jira": "", "status": "pending", "priority": "normal",
     "working_on": "", "next": "write README", "blocked_by": "waiting on Lab team"},
    {"id": "C", "title": "Alarm cleanup", "jira": "DEMO-3", "status": "active", "priority": "high",
     "working_on": "", "next": "", "blocked_by": ""},
]
NONE = {"q": "", "status": "", "prio": ""}
ids = lambda found: [p["id"] for p in found]


def test_no_filters_keeps_everything(js):
    assert ids(js("filterProjects", PROJECTS, NONE)) == ["A", "B", "C"]


@pytest.mark.parametrize("q, found", [
    ("radio", ["A"]),          # title, any case
    ("demo-3", ["C"]),         # Jira key
    ("TEST PLAN", ["A"]),      # working on
    ("readme", ["B"]),         # next step
    ("lab team", ["B"]),       # blocked by
    ("  alarm ", ["C"]),       # spaces around the words are ignored
    ("nothing like it", []),
])
def test_search_box(js, q, found):
    assert ids(js("filterProjects", PROJECTS, {**NONE, "q": q})) == found


def test_dropdowns_and_search_must_all_match(js):
    assert ids(js("filterProjects", PROJECTS, {**NONE, "status": "active"})) == ["A", "C"]
    assert ids(js("filterProjects", PROJECTS, {**NONE, "status": "active", "prio": "high"})) == ["C"]
    assert ids(js("filterProjects", PROJECTS, {"q": "radio", "status": "active", "prio": "high"})) == []


def test_filters_on(js):
    assert js("filtersOn", NONE) is False
    assert js("filtersOn", {**NONE, "q": "   "}) is False      # only spaces typed = no search
    assert js("filtersOn", {**NONE, "prio": "high"}) is True


# ---------- which message an empty list shows ----------

@pytest.mark.parametrize("passed, in_tile, filters_on, message", [
    (5, 2, True, None),           # rows to show: no message
    (0, 0, True, "nomatch"),      # the filters hide everything: "No projects match" + Clear filters
    (3, 0, True, "empty"),        # the filters leave projects, the chosen tile has none of them: "Nothing here."
    (0, 0, False, "empty"),       # no open projects at all
    (4, 0, False, "empty"),
])
def test_empty_list_message(js, passed, in_tile, filters_on, message):
    assert js("emptyMessage", passed, in_tile, filters_on) == message
