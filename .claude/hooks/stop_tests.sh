#!/bin/bash
# Stop hook: when Claude tries to end its turn, run the tests if any .py file changed.
# Red tests -> exit 2 = block the stop and send the failures back to Claude.
# Escape hatches: a SKIP_STOP_HOOK file in the project, or no .py change since the last run.

cd "$CLAUDE_PROJECT_DIR" || exit 0
[ -f SKIP_STOP_HOOK ] && exit 0

state=.claude/.last-tested
now=$(find . -name '*.py' -not -path './.venv/*' -print0 | sort -z | xargs -0 shasum 2>/dev/null | shasum)
[ -f "$state" ] && [ "$(cat "$state")" = "$now" ] && exit 0
echo "$now" > "$state"

out=$(PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q 2>&1)
code=$?
# 0 = all passed, 5 = no tests collected yet
[ $code -eq 0 ] || [ $code -eq 5 ] && exit 0

echo "Tests are red. Fix them, or report them red to the user. Output:" >&2
echo "$out" | tail -40 >&2
exit 2
