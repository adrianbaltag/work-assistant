"""Install test for the ticket-flow plugin. Temporary: goes away when the real hooks move in.

Runs when a Claude Code session starts. It only reports where it runs from, so we learn three things
on each laptop: does Python start, was the plugin copied or read in place, and can the hook still
find the Work Assistant folder (settings.ini, notes.py). It changes nothing.
"""
import json
import os
import sys
from pathlib import Path

here = Path(__file__).resolve()
plugin_root = here.parent.parent            # ticket-flow/
repo = plugin_root.parent                   # the Work Assistant folder, if the plugin was read in place

facts = [
    "PLUGIN-TEST ticket-flow hook ran.",
    f"python {sys.version_info.major}.{sys.version_info.minor} at {sys.executable}",
    f"script at {here}",
    f"CLAUDE_PLUGIN_ROOT = {os.environ.get('CLAUDE_PLUGIN_ROOT', '(not set)')}",
    f"CLAUDE_PLUGIN_DATA = {os.environ.get('CLAUDE_PLUGIN_DATA', '(not set)')}",
    f"notes.py next to the plugin folder: {(repo / 'notes.py').is_file()}",
    f"settings.ini next to the plugin folder: {(repo / 'settings.ini').is_file()}",
]
text = " | ".join(facts)
sys.stdout.write(json.dumps({
    "systemMessage": text,
    "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
}))
