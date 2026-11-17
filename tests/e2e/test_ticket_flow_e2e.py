"""End to end: the plugin's starter script, started for real, runs the real hook file with the real Python.

The plugin is copied to a made-up cache folder (as on the Mac), a pointer file leads to a made-up Work
Assistant folder with copies of the three hook files, and a made-up ticket waits for its creator.
Nothing here touches your real folders or the network.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
WAITING = "# DEMO-42 — requirements\n\n**Status:** WAITING FOR CREATOR (since 2026-11-14)\n"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the made-up .venv is a link to Python: needs a Mac or Linux")


@pytest.fixture
def box(tmp_path):
    """(starter script in the copied plugin, environment for it, the made-up ticket folder)."""
    plugin = tmp_path / "cache" / "ticket-flow"
    shutil.copytree(REPO / "ticket-flow", plugin)
    home = tmp_path / "work-assistant"
    home.mkdir()
    for name in ("work_jira_hooks.py", "project_note.py", "notes.py"):
        shutil.copy(REPO / name, home / name)
    (home / ".venv" / "bin").mkdir(parents=True)
    (home / ".venv" / "bin" / "python").symlink_to(sys.executable)
    ticket = tmp_path / "work_jira" / "DEMO-42"
    ticket.mkdir(parents=True)
    (ticket / "requirements.md").write_text(WAITING, encoding="utf-8")
    (tmp_path / "projects").mkdir()
    (home / "settings.ini").write_text(f"projects_folder={tmp_path / 'projects'}\n"
                                       f"work_jira_folder={tmp_path / 'work_jira'}\n", encoding="utf-8")
    claude = tmp_path / "claude"
    claude.mkdir()
    (claude / "ticket-flow-home.txt").write_text(str(home), encoding="utf-8")
    return plugin / "scripts" / "run_hook.py", {**os.environ, "CLAUDE_CONFIG_DIR": str(claude)}, ticket


def hook(box, word, event):
    script, env, _ = box
    return subprocess.run([sys.executable, str(script), word], input=json.dumps(event), env=env,
                          capture_output=True, text=True, timeout=30)


def test_the_gate_stops_code_and_lets_a_note_through(box):
    ticket = box[2]
    code = hook(box, "gate", {"session_id": "e2e", "tool_name": "Write", "tool_input": {"file_path": str(ticket / "report.py")}})
    answer = json.loads(code.stdout)["hookSpecificOutput"]      # a "deny" answer, not exit 2: no red "hook error" label
    assert (code.returncode, code.stderr, answer["permissionDecision"]) == (0, "", "deny")
    assert "Not written: report.py" in answer["permissionDecisionReason"]
    assert "ticket-flow:clear-ticket" in answer["permissionDecisionReason"]
    note = hook(box, "gate", {"session_id": "e2e", "tool_name": "Write", "tool_input": {"file_path": str(ticket / "tracking_log.md")}})
    assert (note.returncode, note.stdout, note.stderr) == (0, "", "")


def test_every_prompt_gets_its_reminder_through_the_starter(box):
    done = hook(box, "prompt", {"session_id": "e2e", "cwd": str(box[2])})
    assert done.returncode == 0
    assert "ONE step" in json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]


def test_without_the_pointer_file_the_user_is_told_and_nothing_is_stopped(box):
    script, env, ticket = box
    (Path(env["CLAUDE_CONFIG_DIR"]) / "ticket-flow-home.txt").unlink()
    start = hook(box, "session-start", {"session_id": "e2e", "cwd": str(ticket), "source": "startup"})
    assert start.returncode == 0 and "check_setup.py" in json.loads(start.stdout)["systemMessage"]
    code = hook(box, "gate", {"session_id": "e2e", "tool_name": "Write", "tool_input": {"file_path": str(ticket / "report.py")}})
    assert (code.returncode, code.stdout, code.stderr) == (0, "", "")
