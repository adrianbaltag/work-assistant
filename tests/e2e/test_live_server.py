"""The little web server the browser tests use (conftest.py): its two safety promises.

No browser needed here, so these run on every laptop.
"""
import gc
import json
import urllib.error
import urllib.request
import warnings

import pytest

from conftest import serve


def ask_claude(url):
    """Send one Ask Claude question to the test server, like the page would."""
    body = json.dumps({"question": "what is open?", "history": []}).encode("utf-8")
    request = urllib.request.Request(url + "/api/ask", data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=5).close()
    except urllib.error.HTTPError:
        pass                # the app answers with an error page; the point is what the server does after


def test_a_call_to_claude_fails_the_test_even_though_the_app_swallows_the_error(folders):
    with pytest.raises(AssertionError, match="Claude"):
        with serve(*folders) as url:
            ask_claude(url)


def test_no_claude_call_means_no_complaint(folders):
    with serve(*folders) as url:
        urllib.request.urlopen(url + "/api/projects", timeout=5).close()


def test_the_server_closes_its_own_port_and_does_not_leave_that_to_python(folders):
    # A port that is left open makes Python warn "unclosed socket" when it tidies up later.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with serve(*folders):
            pass
        gc.collect()
    left_open = [str(w.message) for w in caught if issubclass(w.category, ResourceWarning)]
    assert left_open == []
