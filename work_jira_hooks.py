"""Claude Code hooks that keep the dashboard in step with work_jira. Pure Python, no Flask, no tokens.

Set up once in your user settings (~/.claude/settings.json, see README):
    python work_jira_hooks.py stop            after every Claude reply
    python work_jira_hooks.py session-start   when a Claude Code session starts
    python work_jira_hooks.py prompt          when you send a prompt (UserPromptSubmit)
    python work_jira_hooks.py after-edit      after Claude edits or writes a file (PostToolUse)
    python work_jira_hooks.py session-end     when the session ends

Milestone guard: one milestone per session. session-start writes a notepad in the ticket's .claude folder
(which milestones in requirements.md were ticked at the start); a box ticked since then = this session's milestone.

Claude Code sends the hook a small JSON on stdin (we use "cwd" = the folder Claude is in).
Exit 0 = all fine. Exit 2 (Stop only) = Claude must keep going: our stderr message tells it what to do.
Any other problem = exit 1, which Claude Code shows but never blocks on.
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path, PurePath

import notes
import project_note as pn

HELPER = Path(__file__).with_name("project_note.py")

CREATE_CARD = """This project has no dashboard card yet. Create it now with one command, then carry on:
  {python} {helper} create {name} --title "<short project name>" --goal "<one or two lines: what this project must achieve>"
{powershell}Don't edit the dashboard note.md by hand: the hooks keep it in sync."""

POWERSHELL = "In PowerShell, put & and a space in front of that command (the first path is in quotes).\n"

NEW_FOLDER = """This is a new project folder: {name}. Before anything else, set it up with the same md set every \
project has, copied from {templates} (CLAUDE.md, requirements.md, tracking_log.md and the rest).{ticket} \
Only set up the md set this session. Then STOP and tell the user to start a new Claude session: \
clear-requirements and grill-me come in that new session. Once tracking_log.md exists, a hook keeps the dashboard card in sync."""

READ_TICKET = " Read ticket.md first: it holds the Jira description the user pasted."

OLD_FOLDER = """This project folder ({name}) is missing its md set (no tracking_log.md). Before other work, create \
the missing md files from {templates}, filled in from what is already in the folder. \
Do not run clear-requirements or grill-me unless the user asks."""

NO_MILESTONES = """This project ({name}) has no milestones in requirements.md yet, and it is not PENDING. \
Before other work, ask the user whether to run the clear-requirements skill now (then grill-me) to write them."""

NO_GIT = """This folder ({name}) has no local git yet, so /close-out and /code-review have no diff. \
Before other work, offer the user to set it up. Only after they say yes: \
1. If there is no .gitignore here, copy {gitignore} here. If that file is missing too, stop and tell the user \
to do the ".gitignore for ticket folders" step in the work-assistant README. \
2. git init, then git add ., then git commit -m "Start local history". \
Never push. If the commit fails because git does not know who the user is, tell them to do the "git name" step \
in the work-assistant README. If they say no, carry on; you will ask again next session."""

PHASE_SKILLS = {        # phase number -> (name, our own skills for it; README "Own skills"). 1 and 5 have none.
    "2": ("2-Plan", ["writing-plans"]),
    "3": ("3-Build", ["test-driven-development", "verification-before-completion"]),
    "4": ("4-Review", ["receiving-code-review", "verification-before-completion"]),
}

USE_SKILLS = "Phase {phase}: use these skills when they apply: {skills}."

PHASE_NOT_SET = """The Phase line in this ticket's CLAUDE.md is not set. Before other work, suggest a phase \
(1-Understand, 2-Plan, 3-Build, 4-Review, 5-Handover) from requirements.md, ask the user to confirm it, \
write it in CLAUDE.md, then carry on."""

ONE_STEP = "When the user must act: give ONE step, then wait for their result."

FINISHED = "{ids} ticked this session. One milestone per session: do not start the next one; tell the user to start a new session."

TICKED = """{ids} ticked in requirements.md. Finish this milestone now, in this order:
1. Code milestone: run /code-review low on its files if not done yet; fix the findings or list them in tracking_log.md.
2. tracking_log.md: under ## Last update add `{today} — {ids} ticked, <proof>`; put the next unticked milestone \
under ## Now working on and the one after it under ## Next up.
3. If the phase changed, update Phase in the ticket CLAUDE.md.
4. If this folder has .git: git add . then git commit -m "{ids} — <what it delivers>". Never push.
5. Tell the user what's next, then STOP. One milestone per session: do not start the next one.
A "user check" milestone is ticked only after the user confirmed it in chat. If they haven't, untick it and ask them."""

LOG_NOT_UPDATED = "{ids} ticked this session, but tracking_log.md is not updated yet: {todo}. Then tell the user what's next and stop."

NOTEPAD_DAYS = 2        # notepads left behind (crash, window closed hard) are deleted at a later session start


def stop(event, settings, now):
    """After every Claude reply. Returns (exit code, message for Claude)."""
    projects, work_jira = settings_paths(settings)
    cwd = event.get("cwd") or os.getcwd()
    work = pn.work_project(work_jira, cwd)
    if work is None:
        if work_jira and pn.same_folder(Path(cwd).resolve(), Path(work_jira).resolve()):
            sync_all(projects, work_jira, now)       # whole work_jira open (old way): sync quietly, never ask
        return 0, ""
    if not (work / pn.TRACKING_LOG).is_file():
        return 0, ""                                 # still being set up: SessionStart already said what to do
    said = [m for m in (card_check(projects, work, now), milestone_check(work, event, now)) if m]
    if said and not event.get("stop_hook_active"):   # never block twice in a row (no loops)
        return 2, "\n\n".join(said)
    return 0, ""


def card_check(projects, work, now):
    """Keep the project's dashboard card in sync. Returns what Claude must do, or "" (nothing)."""
    try:
        card = notes.find_project(projects, work.name)
        archived = None if card else pn.newest_archived(projects, work.name)
        if archived and pn.last_event(archived / notes.NOTE_FILE) == pn.MOVED_TO_PROD:
            pn.create(projects, work, "", "", now)   # folder came back from prod: restore the card, no Claude needed
        elif archived:
            return ""                                # you archived it yourself: it stays archived
        elif card is None:
            python = quoted(Path(sys.executable))
            return CREATE_CARD.format(python=python, helper=quoted(HELPER), name=work.name,
                                      powershell=POWERSHELL if python.startswith('"') else "")
        elif pn.needs_sync(card, work):
            pn.sync(projects, work, now)
    except pn.SyncError as err:
        return f"Dashboard sync: {err}"
    return ""


def milestone_check(work, event, now):
    """After a tick this session: is tracking_log.md updated? Returns what is missing, or "".

    Asked once per milestone per session (the notepad remembers), so a later reply is never held up again.
    """
    file = notepad_file(work, event.get("session_id"))
    data = read_notepad(file) if file else None
    if data is None:
        return ""
    milestones = pn.folder_milestones(work)
    new = [m for m in new_ticks(milestones, data) if m not in data["log_asked"]]
    if not new:
        return ""
    try:
        log = pn.read_tracking_log((work / pn.TRACKING_LOG).read_text(encoding="utf-8-sig"))
    except pn.SyncError:
        return ""                                    # card_check already asks to fix the headings
    today = now.strftime("%Y-%m-%d")
    todays = [entry[1] for entry in map(lambda line: pn.last_update(line, now), log["last"])
              if entry and entry[0] == today]
    after = [m for m, ticked in milestones.items() if not ticked]
    todo = []
    for m in new:
        if not any(re.search(rf"\b{m}\b.*\b(ticked|done)\b", text, re.I) for text in todays):
            todo.append(f"under ## Last update add `{today} — {m} ticked, <proof>`")
        if names(log["now"], m):
            todo.append(f"## Now working on still names {m}: put {after[0] if after else 'what comes next'} there "
                        "and the one after it under ## Next up")
    data["log_asked"] += new
    write_notepad(file, data)
    return LOG_NOT_UPDATED.format(ids=", ".join(new), todo="; ".join(todo)) if todo else ""


def names(text, milestone):
    """Does the text start with this milestone? "M3 — extend the M2 parser" names M3, not M2."""
    return bool(re.match(rf"[\s*-]*{milestone}\b", text, re.I))


def sync_all(projects, work_jira, now):
    """Sync every card whose work_jira folder has a newer tracking_log.md. Problems are skipped silently."""
    for folder in Path(work_jira).iterdir():
        card = notes.find_project(projects, folder.name)
        if card and pn.is_project_folder(folder) and pn.needs_sync(card, folder):
            try:
                pn.sync(projects, folder, now)
            except (pn.SyncError, OSError):
                pass


def session_start(event, settings, now):
    """When a session starts. Returns (context for Claude, note for the user); "" = nothing to say."""
    projects, work_jira = settings_paths(settings)
    gone = pn.archive_gone(projects, work_jira, now)
    added = pn.import_missing(projects, work_jira, now)
    said = []
    if gone:
        said.append(f"Dashboard: moved {', '.join(gone)} to the Archive page (folder no longer in work_jira).")
    if added:
        start = "Added" if said else "Dashboard: added"
        said.append(f"{start} cards for {', '.join(added)} (folders in work_jira).")
    for_user = " ".join(said)

    work = pn.work_project(work_jira, event.get("cwd") or os.getcwd())
    if work is None:
        return "", for_user
    start_notepad(work, event, now)
    templates = Path(work_jira) / "_templates"
    if (work / pn.TRACKING_LOG).is_file():
        return ticket_context(work, templates), for_user
    files = {f.name for f in work.iterdir() if not f.name.startswith(".")}
    if files <= {"ticket.md"}:
        ticket = READ_TICKET if files else ""
        return NEW_FOLDER.format(name=work.name, templates=templates, ticket=ticket), for_user
    return OLD_FOLDER.format(name=work.name, templates=templates), for_user


def ticket_context(work, templates):
    """For a set-up ticket: the local git offer, the phase's skills (or ask to set the phase), then the
    no-milestones nag. PENDING = nothing."""
    if paused(work):
        return ""
    phase = phase_of(work)
    said = []
    if not (work / ".git").exists():
        said.append(NO_GIT.format(name=work.name, gitignore=templates / ".gitignore"))
    if phase == "?":
        said.append(PHASE_NOT_SET)
    elif phase in PHASE_SKILLS:
        name, skills = PHASE_SKILLS[phase]
        said.append(USE_SKILLS.format(phase=name, skills=", ".join(skills)))
    if not pn.folder_milestones(work):
        said.append(NO_MILESTONES.format(name=work.name))
    return " ".join(said)


def paused(work):
    """True when tracking_log.md says PENDING, or its headings are broken (the Stop hook asks to fix them first)."""
    try:
        log = pn.read_tracking_log((work / pn.TRACKING_LOG).read_text(encoding="utf-8-sig"))
    except pn.SyncError:
        return True
    return pn.status_from(log["now"])[0] == "pending"


def phase_of(work):
    """Phase number "1".."5" from the ticket CLAUDE.md's "- **Phase:** 3-Build" line.
    "?" = the line is there but not set (template "1-Understand | 2-Plan | ..." or no number). None = no Phase line."""
    try:
        text = (work / "CLAUDE.md").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        found = re.match(r"[\s*-]*phase\s*:[\s*]*(.*)", line, re.I)
        if found:
            value = found.group(1)
            number = re.match(r"([1-5])(?!\d)", value)
            return number.group(1) if number and "|" not in value else "?"
    return None


# ---------- milestone guard: the notepad ----------

def notepad_file(work, session_id):
    """<ticket>/.claude/milestone-<session id>.json, or None if the session id is missing or odd."""
    session_id = str(session_id or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        return None
    return Path(work) / ".claude" / f"milestone-{session_id}.json"


def start_notepad(work, event, now):
    """Note which milestones are ticked now. compact/resume = the same session goes on: keep the old notepad."""
    file = notepad_file(work, event.get("session_id"))
    if file is None or not (work / pn.REQUIREMENTS).is_file():
        return                                       # requirements.md still to be written: nothing to guard yet
    for old in file.parent.glob("milestone-*.json") if file.parent.is_dir() else []:
        try:
            if now.timestamp() - old.stat().st_mtime > NOTEPAD_DAYS * 24 * 3600:
                old.unlink()
        except OSError:
            pass                                     # open in another window: next time
    if event.get("source") in ("compact", "resume") and file.is_file():
        return
    try:
        file.parent.mkdir(exist_ok=True)
        write_notepad(file, {"ticked": [m for m, done in pn.folder_milestones(work).items() if done], "told": [], "log_asked": []})
    except OSError:
        pass                                         # no notepad = no milestone checks this session, never a wrong block


def read_notepad(file):
    """{"ticked": [at the start], "told": [checklist given], "log_asked": [Stop asked]}, or None (none / unreadable)."""
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        return {key: list(data.get(key, [])) for key in ("ticked", "told", "log_asked")}
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def write_notepad(file, data):
    file.write_text(json.dumps(data), encoding="utf-8")


def new_ticks(milestones, data):
    """Milestones ticked since the session started (read_milestones dict, notepad data), in file order."""
    return [m for m, done in milestones.items() if done and m not in data["ticked"]]


def find_notepad(cwd, session_id):
    """This session's notepad in cwd or a folder above it (Claude may have cd'd into tests\\), or None."""
    here = Path(cwd or os.getcwd())
    for folder in [here, *here.parents]:
        file = notepad_file(folder, session_id)
        if file is None:
            return None
        if file.is_file():
            return file
    return None


def prompt(event):
    """Every prompt you send: the one-step reminder, plus "start a new session" after a tick."""
    file = find_notepad(event.get("cwd"), event.get("session_id"))
    data = read_notepad(file) if file else None
    if data is None:
        return ONE_STEP
    os.utime(file)                                   # still in use: the 2-day clean-up must not delete it
    new = new_ticks(pn.folder_milestones(file.parent.parent), data)
    return f"{ONE_STEP} {FINISHED.format(ids=', '.join(new))}" if new else ONE_STEP


def after_edit(event, now):
    """After Claude edits a file: if it just ticked a new box in the ticket's requirements.md, the checklist (once)."""
    path = (event.get("tool_input") or {}).get("file_path") or ""
    if Path(path).name.casefold() != pn.REQUIREMENTS:
        return ""
    work = Path(path).parent
    file = notepad_file(work, event.get("session_id"))
    data = read_notepad(file) if file else None
    if data is None:
        return ""
    new = [m for m in new_ticks(pn.folder_milestones(work), data) if m not in data["told"]]
    if not new:
        return ""
    data["told"] += new
    write_notepad(file, data)
    return TICKED.format(ids=", ".join(new), today=now.strftime("%Y-%m-%d"))


def session_end(event):
    """Throw this session's notepad away. Claude Code gives this hook very little time: nothing else here."""
    file = find_notepad(event.get("cwd"), event.get("session_id"))
    if file:
        file.unlink(missing_ok=True)


def settings_paths(settings):
    """(projects_folder, work_jira_folder). A bad projects_folder= stops the hook (exit 1, message shown to you)."""
    projects, work_jira = settings.get("projects_folder", "").strip(), settings.get("work_jira_folder", "").strip()
    if work_jira and not (projects and Path(projects).is_dir()):
        raise SystemExit("settings.ini projects_folder= is empty or not a folder. "
                         "Set it to your dashboard projects folder; until then the dashboard is not updated.")
    return projects, work_jira


def quoted(path):
    """A path ready to paste into a command. Forward slashes: Git Bash eats backslashes, PowerShell and cmd don't mind.

    A path with a space gets quotes; PowerShell then needs & in front to run it (see POWERSHELL).
    """
    path = path.as_posix() if isinstance(path, PurePath) else Path(path).as_posix()
    return f'"{path}"' if " " in path else path


def main(argv, stdin=sys.stdin, settings_path=notes.SETTINGS_FILE, now=None):
    which = argv[0] if argv else ""
    try:
        raw = stdin.buffer.read().decode("utf-8") if hasattr(stdin, "buffer") else stdin.read()
        event = json.loads(raw or "{}")
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}
    if which in ("prompt", "after-edit", "session-end"):
        return milestone_main(which, event, now or datetime.now())
    try:
        settings = notes.load_settings(settings_path)
        if which == "stop":
            code, message = stop(event, settings, now or datetime.now())
            if message:
                print(message, file=sys.stderr)
            return code
        if which == "session-start":
            context, for_user = session_start(event, settings, now or datetime.now())
            out = {}
            if context:
                out["hookSpecificOutput"] = {"hookEventName": "SessionStart", "additionalContext": context}
            if for_user:
                out["systemMessage"] = for_user
            if out:
                print(json.dumps(out))
            return 0
        print("work_jira_hooks.py needs one word: stop, session-start, prompt, after-edit or session-end",
              file=sys.stderr)
        return 1
    except SystemExit as err:            # settings.ini missing
        print(f"work_jira hook: {err}", file=sys.stderr)
        return 1
    except Exception as err:             # never block Claude because of a bug or a locked file here
        print(f"work_jira hook problem (Claude can carry on): {err}", file=sys.stderr)
        return 1


def milestone_main(which, event, now):
    """The hooks that need no settings.ini. They never block Claude: a problem here only skips a check."""
    context, event_name = "", ""
    try:
        if which == "prompt":
            event_name = "UserPromptSubmit"
            context = prompt(event)
        elif which == "after-edit":
            event_name = "PostToolUse"
            context = after_edit(event, now)
        else:
            session_end(event)
    except Exception as err:             # a locked or odd file: skip the milestone check, keep the reminder
        print(f"work_jira milestone hook skipped a check ({err}). Claude can carry on. If this keeps coming back, "
              "close other Claude windows on this project, then delete the milestone-*.json files in its .claude "
              "folder.", file=sys.stderr)
        context = ONE_STEP if which == "prompt" else ""
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")    # Windows pipes default to an old code page
    sys.exit(main(sys.argv[1:]))
