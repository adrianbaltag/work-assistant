"""The ticket-flow plugin's hooks: hooks/hooks.json and the starter script scripts/run_hook.py.

The hook code itself stays in work_jira_hooks.py, in the Work Assistant folder. The plugin may be read in
place (the starter sits inside that folder) or copied to Claude Code's cache (it does not), so the starter
has to find the folder both ways. Folders are fake (tmp_path); nothing is started for real here.
"""
import importlib.util
import io
import json
import shutil
from pathlib import Path

import pytest

import check_setup
import work_jira_hooks as hooks

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "ticket-flow"
WORDS = {"Stop": "stop", "SessionStart": "session-start", "UserPromptSubmit": "prompt",
         "PostToolUse": "after-edit", "SessionEnd": "session-end", "PreToolUse": "gate"}


def load_starter(script=PLUGIN / "scripts" / "run_hook.py"):
    """Import run_hook.py from its file (it is not on the import path: Claude Code runs it as a script)."""
    spec = importlib.util.spec_from_file_location("run_hook", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


starter = load_starter()


def fake_home(tmp_path, venv="bin/python"):
    """A made-up Work Assistant folder: the hook file and (unless venv=None) its own Python."""
    home = tmp_path / "work-assistant"
    home.mkdir()
    (home / "work_jira_hooks.py").write_text("# the hooks\n", encoding="utf-8")
    if venv:
        python = home / ".venv" / venv
        python.parent.mkdir(parents=True)
        python.write_text("", encoding="utf-8")
    return home


def copied_plugin(tmp_path):
    """The plugin as Claude Code copies it to its cache: no Work Assistant folder around it."""
    root = tmp_path / "cache" / "work-assistant" / "ticket-flow" / "0.1.0"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    return root


def pointer(tmp_path, text):
    claude = tmp_path / "claude"
    claude.mkdir(exist_ok=True)
    (claude / starter.POINTER).write_text(text, encoding="utf-8")
    return claude


# ---------- hooks.json ----------

def hook_entries():
    events = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    return {event: groups for event, groups in events.items()}


def test_the_plugin_runs_all_six_hooks_through_the_starter():
    entries = hook_entries()
    assert set(entries) == set(WORDS)
    for event, word in WORDS.items():
        (group,) = entries[event]
        (hook,) = group["hooks"]
        assert hook["type"] == "command" and hook["command"] == "python"         # no shell: a real program + args
        assert hook["args"] == ["${CLAUDE_PLUGIN_ROOT}/scripts/run_hook.py", word]


def test_every_word_in_hooks_json_is_one_the_hook_file_knows(tmp_path, capsys):
    ini = tmp_path / "settings.ini"
    ini.write_text("projects_folder=\nwork_jira_folder=\n", encoding="utf-8")
    for word in WORDS.values():
        hooks.main([word], io.StringIO("{}"), ini)
        assert "needs one word" not in capsys.readouterr().err


def test_the_gate_runs_before_every_tool_that_writes_a_file():
    (group,) = hook_entries()["PreToolUse"]
    assert set(group["matcher"].split("|")) == {"Write", "Edit", "MultiEdit", "NotebookEdit"}
    (after,) = hook_entries()["PostToolUse"]
    assert {"Write", "Edit", "MultiEdit"} <= set(after["matcher"].split("|"))


def test_session_end_gets_more_than_the_short_default_time():
    """Claude Code gives SessionEnd 1.5 seconds unless the hook asks for more, and two Pythons start here."""
    assert hook_entries()["SessionEnd"][0]["hooks"][0]["timeout"] >= 10


def test_the_install_test_leftovers_are_gone():
    assert not (PLUGIN / "skills" / "hello").exists()
    assert not (PLUGIN / "scripts" / "hello_hook.py").exists()


# ---------- the starter: find the Work Assistant folder ----------

def test_read_in_place_the_folder_is_the_one_around_the_plugin(tmp_path):
    assert starter.find_home(PLUGIN, tmp_path / "no-claude-folder") == REPO


def test_copied_to_the_cache_the_folder_comes_from_the_pointer_file(tmp_path):
    home = fake_home(tmp_path)
    claude = pointer(tmp_path, f"{home}\n")
    assert starter.find_home(copied_plugin(tmp_path), claude) == home


@pytest.mark.parametrize("text", ["", "\n", "{nowhere}", "{no_hooks}"])
def test_no_pointer_or_one_that_leads_nowhere_means_not_found(tmp_path, text):
    (tmp_path / "empty").mkdir()
    text = text.format(nowhere=tmp_path / "gone", no_hooks=tmp_path / "empty")
    assert starter.find_home(copied_plugin(tmp_path), pointer(tmp_path, text)) is None
    assert starter.find_home(copied_plugin(tmp_path), tmp_path / "no-claude-folder") is None


def test_the_starter_and_check_setup_agree_on_the_pointer_file(tmp_path):
    """check_setup.py writes it, the starter reads it: same folder rule, same file name."""
    assert starter.POINTER == check_setup.POINTER
    for env in ({}, {"CLAUDE_CONFIG_DIR": str(tmp_path / "other")}, {"CLAUDE_CONFIG_DIR": "  "}):
        assert starter.claude_folder(env) == check_setup.claude_folder(env)
    assert starter.claude_folder({"CLAUDE_CONFIG_DIR": str(tmp_path / "other")}) == tmp_path / "other"
    assert starter.claude_folder({}) == Path.home() / ".claude"


@pytest.mark.parametrize("venv", ["Scripts/python.exe", "bin/python"])
def test_the_apps_own_python_is_found_on_windows_and_mac(tmp_path, venv):
    home = fake_home(tmp_path, venv)
    assert starter.venv_python(home) == home / ".venv" / venv
    shutil.rmtree(home / ".venv")
    assert starter.venv_python(home) is None


# ---------- the starter: main ----------

class Runner:
    """Stands in for subprocess.run: remembers the command, answers with an exit code or an error."""
    def __init__(self, code=0, error=None):
        self.code, self.error, self.commands = code, error, []

    def __call__(self, command):
        self.commands.append(command)
        if self.error:
            raise self.error
        return self.code


def run(tmp_path, word, home="found", runner=None, venv="bin/python"):
    """Run the starter's main as if copied to the cache. home="found": the pointer leads to a made-up folder."""
    runner = runner or Runner()
    claude = tmp_path / "no-claude-folder"
    if home == "found":
        home = fake_home(tmp_path, venv)
        claude = pointer(tmp_path, str(home))
    code = starter.main([word], plugin_root=copied_plugin(tmp_path), claude=claude, run=runner)
    return code, runner, home


@pytest.mark.parametrize("word", WORDS.values())
def test_the_starter_hands_every_hook_to_the_apps_own_python(tmp_path, word):
    code, runner, home = run(tmp_path, word)
    assert code == 0
    assert runner.commands == [[str(home / ".venv" / "bin" / "python"), str(home / "work_jira_hooks.py"), word]]


@pytest.mark.parametrize("code", [0, 1, 2])
def test_the_starter_passes_the_hooks_answer_on_unchanged(tmp_path, code):
    """Claude Code must get exactly the exit code the hook gave (our hooks give 0 or 1; 2 would block)."""
    assert run(tmp_path, "gate", runner=Runner(code))[0] == code


def test_folder_not_found_says_so_once_at_session_start_and_never_stops_claude(tmp_path, capsys):
    code, runner, _ = run(tmp_path, "session-start", home=None)
    out = capsys.readouterr()
    assert code == 0 and runner.commands == []
    said = json.loads(out.out)["systemMessage"]
    assert "ticket-flow cannot find the Work Assistant folder" in said and "check_setup.py" in said
    for word in ("gate", "stop", "prompt", "after-edit", "session-end"):
        code, runner, _ = run(tmp_path, word, home=None)
        out = capsys.readouterr()
        assert (code, out.out, out.err, runner.commands) == (0, "", "", [])      # quiet, and the write goes ahead


def test_no_python_box_in_the_folder_says_so_at_session_start(tmp_path, capsys):
    code, runner, _ = run(tmp_path, "session-start", venv=None)
    said = json.loads(capsys.readouterr().out)["systemMessage"]
    assert code == 0 and runner.commands == []
    assert ".venv" in said and "INSTALL.md" in said


def test_a_python_that_will_not_start_never_stops_claude(tmp_path, capsys):
    code, _, _ = run(tmp_path, "gate", runner=Runner(error=OSError("cannot start")))
    err = capsys.readouterr().err
    assert code == 1 and "Claude can carry on" in err            # exit 1 = shown, not blocking: the write goes ahead


def test_the_starter_without_a_word_does_nothing(tmp_path):
    runner = Runner()
    assert starter.main([], plugin_root=copied_plugin(tmp_path), claude=tmp_path, run=runner) == 0
    assert runner.commands == []
