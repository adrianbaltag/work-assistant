"""Browser tests: the real page in a real (hidden) browser, on a real local web server.

The server runs the app on made-up folders (tmp_path) and a free port. Nothing here touches your
real notes, the real port 5050 or the network: Claude is a fake that fails if called, and the
browser may only talk to this one local server.
"""
import threading
from contextlib import contextmanager
from datetime import datetime

import pytest
from werkzeug.serving import make_server

import notes
import project_note as pn
from app import create_app

NOW = datetime(2026, 11, 18, 9, 30)
LONG_ENTRY = ("M7 done: the settings page with its folders, the check, save and reset buttons, the archived "
              "companies moved here from under the table, a backup button with a summary, and an about box "
              "with the version and the data folder. All tests are green, the review passed after two rounds "
              "and every step was checked on screen with made-up data")
LONG_NEXT = ("M9 · Release: the start file for Windows, the start file for the Mac, the script that builds the "
             "release, the guide for the people who install it, and the first release on the download page")
LOG = "# DEMO-42 — Tracking log\n\n## Now working on\n{now}\n\n## Next up\nM3 — email the report\n\n## Last update\n{last}\n"


@pytest.fixture
def folders(tmp_path):
    """(projects folder, work_jira folder) with three made-up projects.

    DEMO-1  = a personal card with one long and one short History line and a long Next step.
    DEMO-42 = a card that follows a work folder (tracking_log.md).
    BAD-1   = a card whose note.md is saved in the wrong encoding (ANSI instead of UTF-8).
    """
    projects, work_jira = tmp_path / "projects", tmp_path / "work_jira"
    projects.mkdir()
    card = notes.new_project(projects, "DEMO-1", "Demo one")
    note = card / notes.NOTE_FILE
    text = notes.set_fields(note.read_text(encoding="utf-8"), {"working_on": "M8 of 9 · Email alerts", "next": LONG_NEXT})
    text = notes.add_history(text, "M1 ticked", "2026-11-06", who=pn.WHO)
    notes.safe_write(note, notes.add_history(text, LONG_ENTRY, "2026-11-07", who=pn.WHO))
    work = work_jira / "DEMO-42"
    work.mkdir(parents=True)
    (work / pn.TRACKING_LOG).write_text(LOG.format(now="M2 — parse the alarm file", last="2026-11-17 — M1 ticked"),
                                        encoding="utf-8")
    pn.create(projects, work, "", "", NOW)
    (projects / "BAD-1").mkdir()
    (projects / "BAD-1" / notes.NOTE_FILE).write_bytes("---\ntitle: Café\n---\nbody\n".encode("cp1252"))
    return projects, work_jira


@contextmanager
def serve(projects, work_jira):
    """Run the app on a free port of 127.0.0.1 for as long as the `with` block lasts. Gives the address.

    A browser test must never call Claude. The app turns every error into a plain "something went
    wrong" answer, so an error raised by the fake Claude would be swallowed. That is why each call is
    counted here, and the count is checked when the server stops.
    """
    claude_calls = []

    def no_claude():
        claude_calls.append("called")
        raise AssertionError("a browser test must never call Claude")

    app = create_app(projects, work_jira_folder=str(work_jira), claude=no_claude)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()           # serve_forever also closes the port when it stops
        thread.join()
    assert not claude_calls, f"a browser test must never call Claude, and this one did ({len(claude_calls)} time(s))"


@pytest.fixture
def live_url(folders):
    """The app on a free port of 127.0.0.1 while the test runs."""
    with serve(*folders) as url:
        yield url


@pytest.fixture
def dash(page, live_url):
    """The dashboard, opened in the browser. Anything that is not this local server is blocked (fonts, etc.)."""
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(live_url) else route.abort())
    page.goto(live_url)
    return page
