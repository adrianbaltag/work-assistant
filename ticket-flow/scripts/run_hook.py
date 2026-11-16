"""Starter for the ticket-flow hooks. Claude Code runs it with one word, for example: run_hook.py gate

The hook code itself is not in this plugin. It is work_jira_hooks.py in the Work Assistant folder, next to
settings.ini. This script only finds that folder and hands the hook over to the app's own Python (.venv).

Where the folder is:
1. Around this plugin, when Claude Code reads the plugin in place (the plugin folder sits inside it).
2. Else in the pointer file ticket-flow-home.txt in Claude Code's folder. One line: the folder's path.
   check_setup.py writes it. Needed when Claude Code copied the plugin to its cache.

A problem here never stops Claude: folder not found = one line for you at session start, and every hook
does nothing (so no write is ever stopped by mistake).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK_FILE = "work_jira_hooks.py"
POINTER = "ticket-flow-home.txt"
NOT_FOUND = ("ticket-flow cannot find the Work Assistant folder. Run check_setup.py in that folder. "
             "Until then the ticket-flow hooks do nothing.")
NO_PYTHON = ("ticket-flow found the Work Assistant folder ({home}) but not its own Python (.venv). "
             "Do Step 2 of INSTALL.md in that folder. Until then the ticket-flow hooks do nothing.")


def claude_folder(env):
    """Claude Code's own folder: ~/.claude, unless CLAUDE_CONFIG_DIR says another one."""
    other = (env.get("CLAUDE_CONFIG_DIR") or "").strip()
    return Path(other) if other else Path.home() / ".claude"


def find_home(plugin_root, claude):
    """The Work Assistant folder (the one that holds work_jira_hooks.py), or None."""
    around = Path(plugin_root).parent
    if (around / HOOK_FILE).is_file():
        return around
    try:
        lines = (Path(claude) / POINTER).read_text(encoding="utf-8-sig").split("\n")
    except (OSError, UnicodeDecodeError):
        return None
    written = lines[0].strip()
    if written and (Path(written) / HOOK_FILE).is_file():
        return Path(written)
    return None


def venv_python(home):
    """The app's own Python: .venv\\Scripts\\python.exe on Windows, .venv/bin/python on a Mac. None = no .venv."""
    for inside in ("Scripts/python.exe", "bin/python"):
        python = Path(home) / ".venv" / inside
        if python.is_file():
            return python
    return None


def tell_user(word, message):
    """One line for the person, at session start only: the other hooks run too often to repeat it."""
    if word == "session-start":
        sys.stdout.write(json.dumps({"systemMessage": message}))


def main(argv, plugin_root=None, claude=None, run=None):
    """Returns the exit code for Claude Code: the hook's own answer, or 0 or 1 (never blocking) on a problem here."""
    if not argv:
        return 0
    word = argv[0]
    plugin_root = plugin_root or Path(__file__).resolve().parent.parent
    home = find_home(plugin_root, claude or claude_folder(os.environ))
    if home is None:
        tell_user(word, NOT_FOUND)
        return 0
    python = venv_python(home)
    if python is None:
        tell_user(word, NO_PYTHON.format(home=home))
        return 0
    run = run or (lambda command: subprocess.run(command).returncode)    # the hook reads Claude Code's JSON itself
    try:
        return run([str(python), str(home / HOOK_FILE), word])
    except OSError as err:
        sys.stderr.write("ticket-flow could not start the hook (%s). Claude can carry on.\n" % err)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
