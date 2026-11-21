"""Work Assistant: a local web page over your project notes.

Run it:   python app.py      then open http://127.0.0.1:5050
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

import claude_chat
import dashboard_inbox
import notes
import prod_folder
import project_note
import slack_inbox
import slack_live
import todos
import work_jira_hooks

SETTINGS_FILE = notes.SETTINGS_FILE
load_settings = notes.load_settings     # lives in notes.py so helper scripts can read settings without Flask
PORT = 5050         # not 5000: macOS AirPlay Receiver uses that port
CHOICES = {"status": list(notes.STATUSES), "priority": ["critical", "high", "normal"]}
FORM_FIELDS = ["title", "status", "priority", "working_on", "next", "blocked_by", "jira", "folder"]
UPLOAD_LIMIT_MB = 50
LOCKED = notes.LOCKED
UNREADABLE = "Could not read {}. Is it open in another program (e.g. Excel)? Close it and reload this page (F5)."
FILE_PROBLEM = ("Could not read or change {} ({}). Check that the disk or network drive is there and not full, "
                "then try again.")
TODO_ODD = "The page sent something odd. Reload the page (F5) and try again."
TODO_ROW = {"row": int, "text": str}     # which todo a change is for: its place in todos.md + its words
CRASHED = ("Something went wrong inside the app. Reload the page (F5) and try again. "
           "If it happens again, look at the terminal where the app runs.")

# The card's Note / Blocker / Unblock box (api_message)
MESSAGE_TRIES = 3       # note.md saved by someone else in the same moment: read it again, this many times at most
MESSAGES_SHOWN = 3      # the card lists this many sent messages, newest first
NO_WORDS = "The message is empty. Type a few words first."
NO_BLOCKER = "Your blocker is already off. Reload the page (F5) to see the card as it is now."
BUSY_NOTE = "note.md is being saved by another program right now. Wait a moment, then send it again."
WORK_AWAY = ("Not sent: can't find this project's work folder {} (moved, or the VPN is off). "
             "Nothing was changed. Connect it, then send it again.")
NOT_SENT = ("Not sent: the message could not be left in the work folder ({}). Nothing was changed. "
            "Check that the folder is there and that you may write to it, then send it again.")
HALF_SENT = ("Your message is on the card (see History), but Claude did NOT get it: it could not be left in the "
             "work folder ({}). Tell Claude yourself in its next session.")

# ✓ Complete (api_complete): why a card can't move to Completed yet.
NOT_CLOSED = ("{} is still in progress: its ticket is not closed yet (or it was reopened). Finish it with Claude "
              "(or tell Claude \"this ticket is done\"), then Complete it.")
FOLDER_AWAY = ("Can't see the work folder of {} right now (moved, or the VPN is off). Connect it, "
               "then try Complete again.")
TICKET_UNREADABLE = ("Can't read requirements.md of {}. Is it open in another program? Close it, "
                     "then try Complete again.")
# G3: ✓ Complete moves a ticket folder from work_jira to PROD_SCRIPTS, Restore moves it back. Nothing half done.
NEED_FOLDER = "Choose the folder for completed projects first."
FOLDER_LOCKED = ("Could not move the folder {}: a program has a file open in it (VS Code, Claude Code, Excel ...). "
                 "Close that program, then try again. Nothing moved.")
OTHER_DRIVE = ("Could not move the folder {}: your folder for completed projects is on another drive. Delete the "
               "hidden .work-assistant-completed file in it, click ✓ Complete again and pick a folder on the same "
               "drive as {}. Nothing moved.")
CANT_MAKE = ("Could not make the folder {} or its small hidden file ({}). Type another folder in the box, or check "
             "that you may save files there. Nothing moved.")
NOT_IN_WORK_JIRA = ("The folder of {} is at {}, not in your work_jira folder ({}), so nothing moved. Move the folder "
                    "into work_jira (or fix work_jira_folder= in settings.ini and restart the app), then click "
                    "✓ Complete again.")
ODD_PROD_FOLDER = ("The card says its folder is at {}, which is not a place the app moves folders from (your user "
                   "folder, or work_jira's drive). Nothing moved. Fix or empty the prod_folder: line in the card's "
                   "note.md (in projects\\_archive), then click Restore again.")
STUCK = ("Could not finish the move of {}: its folder is now at {} and could not be put back. Close any program "
         "using it and move it back yourself, then try again.")
RESTORE_CLASH = ("{1} already has a folder named {0}. Restore never overwrites it: rename or move that folder, "
                 "then click Restore again. Nothing moved.")
NO_WORK_JIRA = ("Can't put the folder back from {}: the app can't find your work_jira folder (work_jira_folder= "
                "in settings.ini, or the drive is away). Fix that, restart the app, then click Restore again. "
                "Nothing moved.")
FOLDER_MISSING = "The card is back, but its folder was not at {} (moved or deleted?), so only the card came back."


class Refused(Exception):
    """A message from the card that must not be saved. str(err) = the plain words for the page."""


def history_text(kind, text):
    """The History line of a card message. Its words are the ones Claude gets in the message."""
    if kind == "note":
        return text
    if kind == "blocker":
        return f"Blocker: {text}"
    return f"Unblocked: {text}" if text else "Unblocked"


def folder_is_there(path):
    try:
        return Path(path).is_dir()
    except OSError:         # e.g. a share that refuses us
        return False


class PageSentOdd(Exception):
    """The JSON the page sent is missing something or is not JSON at all. Answered with TODO_ODD."""


class Finding(NamedTuple):
    """One line of the settings check. level = "ok", "bad", "warn" or "skip"."""
    level: str
    text: str
    stops_app: bool = True      # for a "bad" one: the app refuses to start. Not for a folder that is away
                                # (projects_folder: the page says so; work_jira_folder: its box just greys)


def validate_settings(path=None):
    """The one settings check: the app start-up and check_setup.py both use it.

    Returns (settings dict, slack settings, findings). settings is None when settings.ini is missing or
    unreadable (then there is one "bad" finding and the slack settings are the defaults).
    path=None = the real settings.ini. Nothing is raised: every mistake is a Finding in plain English.
    """
    slack = slack_inbox.slack_settings({})
    try:
        settings = load_settings() if path is None else load_settings(path)
    except SystemExit as err:
        return None, slack, [Finding("bad", str(err))]
    found = [Finding("ok", f"settings.ini found ({path or SETTINGS_FILE})")]
    folder = settings.get("projects_folder", "").strip()
    if not folder:
        found.append(Finding("bad", "projects_folder= is empty or missing in settings.ini. Type the path to your "
                                    "notes folder after the =, like C:\\Users\\YOUR-NAME\\Desktop\\projects "
                                    "(Mac: /Users/YOUR-NAME/Desktop/projects)."))
    elif not Path(folder).is_dir():
        found.append(Finding("bad", f"projects_folder= {folder} does not exist. Fix the path in settings.ini "
                                    "(for a network drive: connect the VPN first)." + notes.path_hint(folder),
                             stops_app=False))      # the page opens and says so: a drive that comes back needs no restart
    else:
        try:
            count = len(notes.project_folders(folder))      # counts folders, opens no note: one bad note is not a settings mistake
        except OSError as err:
            found.append(Finding("bad", f"projects_folder= {folder} can't be read ({err.strerror or err}). "
                                        "Check the path, the VPN (for a network drive) and that you may open it.",
                                 stops_app=False))
        else:
            found.append(Finding("ok", f"projects_folder: {folder} ({count} projects)"))
    found.append(check_work_jira_folder(settings.get("work_jira_folder", "").strip()))
    try:
        read_text_limit(settings.get("text_limit", ""))
    except SystemExit as err:
        found.append(Finding("bad", str(err)))
    try:
        slack = slack_inbox.slack_settings(settings)
    except SystemExit as err:
        found.append(Finding("bad", str(err)))
    if settings.get("jira_url", "").strip() and not read_jira_url(settings["jira_url"]):
        found.append(Finding("warn", "jira_url= must start with https:// (or http://). Until then, Open in Jira is off."))
    return settings, slack, found


def check_work_jira_folder(folder):
    """One Finding for work_jira_folder=. Blank is fine: sync with work_jira is optional."""
    if not folder:
        return Finding("skip", "work_jira_folder= not set: sync with work_jira and the Work project box are off (optional).")
    if not Path(folder).is_dir():
        return Finding("bad", f"work_jira_folder= {folder} does not exist. Fix the path in settings.ini, "
                              "or leave it blank to turn sync with work_jira off." + notes.path_hint(folder),
                       stops_app=False)
    try:
        count = sum(1 for f in Path(folder).iterdir() if project_note.is_project_folder(f))
    except OSError as err:
        return Finding("bad", f"work_jira_folder= {folder} can't be read ({err.strerror or err}). "
                              "Check the path and that you may open it.", stops_app=False)
    return Finding("ok", f"work_jira_folder: {folder} ({count} project folders)")


def read_text_limit(value):
    """text_limit= as a number of characters (empty = the default). A bad value stops the app."""
    value = str(value).strip().replace("_", "")
    if not value:
        return claude_chat.TEXT_CAP
    if value.isdecimal() and int(value) > 0:
        return int(value)
    raise SystemExit(f'text_limit= in settings.ini must be a whole number of characters, like 200000 '
                     f'(no commas). It is "{value}".')


def read_projects_folder(value):
    """projects_folder= without spaces around it. Empty stops the app (it would quietly list its own folder)."""
    value = value.strip()
    if not value:
        raise SystemExit("projects_folder= is empty in settings.ini. Type the path to your notes folder after the =, "
                         "like C:\\Users\\YOUR-NAME\\Desktop\\projects (Mac: /Users/YOUR-NAME/Desktop/projects), "
                         "then start the app again.")
    return value


def read_jira_url(value):
    """jira_url= without a trailing /, or "" (Open in Jira off) when it isn't a web address."""
    value = value.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        return ""       # "jira.example.com" alone would open as a page of this app, not Jira
    return value


def ready_to_complete(project):
    """Can this dashboard row move to Completed, and why. The page shows "✓ Complete" for any of the first three.

    "no_ticket"        a card with no work folder: you decide when it is done
    "closed"           its ticket is closed: the newest ## Closed / ## Reopened heading in requirements.md is
                       ## Closed (in any ticket, old ones too)
    "no_requirements"  its work folder has no requirements.md (yet): you decide, the page asks first
    "old_ticket"       a ticket from before ticket-flow (no Status line): it never gets one, so you decide
    ""                 the ticket is still open: the grey "In progress" label
    "away"             the work folder can't be seen right now (moved, VPN off): also grey
    "unreadable"       its requirements.md can't be read (open in another program?): also grey, logged
    Runs for every row on every refresh, so one bad folder never raises: it greys only its own row.
    """
    work = notes.linked_folder(project)
    if not work:
        return "no_ticket"
    if not Path(work).is_dir():
        return "away"
    try:
        text = project_note.requirements_text(work)
    except OSError as err:
        notes.log_once(f"Complete check of {work}", f"can't read requirements.md ({err.strerror or err})")
        return "unreadable"
    notes.log_once(f"Complete check of {work}", None)
    if work_jira_hooks.is_closed(text):
        return "closed"
    return {"new": "no_requirements", "old": "old_ticket"}.get(work_jira_hooks.state_of_text(text), "")


def move_problem(err):
    """Plain words for a project folder that could not be moved (✓ Complete, Restore)."""
    if isinstance(err, PermissionError):
        return LOCKED.format("the project folder")
    return FILE_PROBLEM.format("the project folder", err.strerror or err)


def folder_problem(err, name, work_jira):
    """Plain words for a ticket folder that could not move between work_jira and PROD_SCRIPTS."""
    if isinstance(err, PermissionError):
        return FOLDER_LOCKED.format(name)
    if prod_folder.other_drive(err):
        return OTHER_DRIVE.format(name, work_jira)
    return FILE_PROBLEM.format(f"the folder {name}", err.strerror or err)


def open_in_file_manager(path):
    """Show a folder in Windows Explorer (Finder on a Mac). Tests swap this for a fake."""
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)], check=True)


def create_app(projects_folder=None, jira_url="", claude=claude_chat.make_client, model="", text_limit="",
               slack=None, work_jira_folder="", home=None):
    """Build the Flask app. No folder given = a real run: read it (and jira_url, model, text_limit,
    the slack_ lines) from settings.ini, and start the Slack part.

    claude = a function that returns the Claude client; tests pass one that returns a fake.
    slack = the running Slack part (slack_live.Live); tests pass a fake, or none = "not connected".
    work_jira_folder = where + New project also makes a folder when "Work project" is ticked ("" = box greyed).
    home = the user folder, where PROD_SCRIPTS is searched for and must be (tests pass a fake one).
    """
    slack_settings = None
    if projects_folder is None:
        settings, slack_settings, findings = validate_settings()
        stops = [f.text for f in findings if f.level == "bad" and f.stops_app]
        if stops:       # one short message with every mistake: SystemExit prints it, no traceback
            raise SystemExit("Work Assistant did not start. Fix this in settings.ini, then start it again "
                             "(python check_setup.py checks everything):\n- " + "\n- ".join(stops))
        projects_folder = read_projects_folder(settings.get("projects_folder", ""))
        jira_url = settings.get("jira_url", "")
        model = settings.get("model", "")
        text_limit = settings.get("text_limit", "")
        work_jira_folder = settings.get("work_jira_folder", "")
    model = model.strip() or claude_chat.DEFAULT_MODEL
    work_jira_folder = work_jira_folder.strip()
    user_home = Path(home) if home else Path.home()     # (a route below is called home)
    # work_jira on another drive (D:): PROD_SCRIPTS may be on that drive too, as a move between drives fails
    work_root, work_near = prod_folder.work_drive(user_home, work_jira_folder)
    prod_roots = [work_root] if work_root else []
    text_limit = read_text_limit(text_limit)
    jira_url = read_jira_url(jira_url)
    if slack_settings is not None:      # last: a bad setting above stops the app with no Slack threads running
        slack = slack_live.start(slack_settings, slack_inbox.Inbox())
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = UPLOAD_LIMIT_MB * 1024 * 1024
    # Only this page's own address. Without it a website can point its own name at 127.0.0.1 (DNS rebinding)
    # and talk to the app: same_site_only below can't tell, because that name is then "the same site".
    app.config["TRUSTED_HOSTS"] = ["127.0.0.1", "localhost"]

    @app.before_request
    def same_site_only():
        """Refuse saves sent by other websites open in the same browser (they could upload or archive files)."""
        origin = request.headers.get("Origin")
        if request.method == "POST" and origin and urlparse(origin).netloc != request.host:
            return jsonify(error="Refused: this request came from another website."), 403

    @app.errorhandler(413)
    def too_big(_):
        return jsonify(error=f"Upload too big ({UPLOAD_LIMIT_MB} MB max at once)."), 413

    @app.errorhandler(PageSentOdd)
    def page_sent_odd(_):
        return jsonify(error=TODO_ODD), 400

    @app.errorhandler(Exception)
    def anything_else(err):
        """Last net: every error the page gets is JSON in plain English, never an HTML traceback page."""
        if isinstance(err, HTTPException):
            return err                      # 404, 413 ... answer as they always did
        if isinstance(err, (UnicodeDecodeError, OSError)):
            app.logger.error("A file could not be read or changed", exc_info=err)     # what failed, for the terminal
        if isinstance(err, UnicodeDecodeError):
            return jsonify(error=notes.NOT_UTF8.format("A note or file in this project")), 400
        if isinstance(err, notes.Locked):
            return jsonify(error=str(err)), 400         # it already names the file
        if isinstance(err, OSError):
            name = Path(err.filename).name if err.filename else "a file"
            if isinstance(err, PermissionError):
                return jsonify(error=LOCKED.format(name)), 400
            return jsonify(error=FILE_PROBLEM.format(name, err.strerror or err)), 400
        app.logger.exception("Unexpected error")      # the details stay in the terminal, not on the page
        return jsonify(error=CRASHED), 500

    def page_json(**fields):
        """The JSON body the page sent, as a dict. fields name=type: each must be there with that type.

        Anything else raises PageSentOdd (a plain message) instead of a KeyError traceback.
        """
        data = request.get_json(silent=True)
        if not (isinstance(data, dict) and all(isinstance(data.get(name), kind) for name, kind in fields.items())):
            raise PageSentOdd()
        return data

    def work_jira_problem():
        """Why the Work project box is off, or "" when work_jira_folder= is set and the folder is there."""
        if not work_jira_folder:
            return "Add work_jira_folder= to settings.ini, then restart the app."
        if not Path(work_jira_folder).is_dir():
            return (f"Can't find the folder {work_jira_folder}. Fix work_jira_folder= in settings.ini, "
                    "then restart the app." + notes.path_hint(work_jira_folder))
        return ""

    @app.get("/")
    def home():
        problem = work_jira_problem()
        return render_template("index.html", work_jira=not problem, work_jira_problem=problem,
                               todo_empty=todos.EMPTY, todo_max=todos.MAX_LENGTH)

    @app.get("/api/projects")
    def api_projects():
        now = datetime.now()
        project_note.sync_all(projects_folder, work_jira_folder, now)     # cards behind their work folder catch up
        try:
            projects = notes.list_projects(projects_folder)
        except OSError as err:
            if Path(projects_folder).is_dir():      # the folder is fine: one file inside it failed
                return jsonify(error=f"Can't read {err.filename or projects_folder} ({err.strerror or err}). "
                                     "Close it if another program has it open, or check that you may open it."), 500
            # The folder itself: e.g. a Windows path in settings.ini on a Mac, or a network drive without VPN.
            return jsonify(error=f"Can't open the projects folder {projects_folder} ({err.strerror or err}). "
                                 "Check projects_folder= in settings.ini (and the VPN, for a network drive). "
                                 "After changing settings.ini, restart the app."
                                 + notes.path_hint(str(projects_folder))), 500
        rows = notes.dashboard(projects, now)
        for row in rows:
            del row["body"]
            row["ready"] = ready_to_complete(row)
        completed = project_note.list_completed(projects_folder)     # never raises: a bad card is left out
        return jsonify(today=now.strftime("%Y-%m-%d"), projects=rows, completed=completed)

    @app.post("/api/projects")
    def api_new_project():
        """+ New project. JSON {id, title, status, work, description, created_by}.

        The ID is cleaned ("my idea" -> "my_idea"; work "abc-123" -> "ABC-123") and becomes the folder.
        work = true: also make work_jira\\<ID>\\ with a ticket.md, and mark the card as following it.
        """
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        project_id = secure_filename(str(data.get("id") or ""))     # "or": a JSON null must not become "None"
        status = str(data.get("status") or "active")
        if not project_id:
            return jsonify(error="Type a ticket ID or a short name (letters, digits, - or _)."), 400
        if status not in notes.NEW_STATUSES:
            return jsonify(error=f"Unknown status: {status}."), 400
        work = data.get("work") is True
        key = project_note.ticket_key(project_id)      # the same rule as the import of a work_jira folder
        if work and key:
            project_id = key                    # work "abc-123" = Jira key ABC-123 (card, folders, jira:)
        problem = work_jira_problem() if work else ""
        if problem:
            return jsonify(error=f"Work project is off. {problem} For a personal idea, untick Work project."), 400
        try:
            notes.new_project(projects_folder, project_id, str(data.get("title") or ""), status)
        except FileExistsError:
            return jsonify(error=f'A folder named "{project_id}" already exists. Pick another name.'), 400
        except ValueError:
            return jsonify(error=f'"{project_id}" can\'t be used as a folder name. Pick another name.'), 400
        except OSError as err:
            return jsonify(error=f"Could not create the folder: {err}. Is the projects folder reachable?"), 400
        if work:
            try:
                folder, made = project_note.start_work_folder(work_jira_folder, project_id,
                                                           str(data.get("description") or ""),
                                                           str(data.get("created_by") or ""))
                project_note.link_card(Path(projects_folder) / project_id, folder)
            except OSError as err:
                return jsonify(error=f"The card {project_id} was made, but not its work_jira folder "
                                     f"({err.strerror or err}). Is {work_jira_folder} reachable? "
                                     "Make the folder there by hand."), 400
            if not made:
                return jsonify(id=project_id, note=f"work_jira\\{project_id}\\ already existed: kept as it was, "
                                                   "so Created by and the description were not saved.")
        return jsonify(id=project_id)

    def folder_or_404(project_id):
        folder = notes.find_project(projects_folder, project_id)
        if folder is None:
            abort(404)
        return folder

    @app.get("/api/projects/<project_id>")
    def api_project(project_id):
        """Everything the project card needs. stamp = note.md's version, sent back on save."""
        folder = folder_or_404(project_id)
        try:
            stamp = notes.note_stamp(folder)     # before reading: a change in between = a warning, not a lost edit
            project = notes.dashboard([notes.read_project(folder)], datetime.now())[0]
            text = (folder / notes.NOTE_FILE).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return jsonify(error=notes.NOT_UTF8.format(f"{project_id}\\{notes.NOTE_FILE}")), 400
        except OSError:
            return jsonify(error=UNREADABLE.format(notes.NOTE_FILE)), 400
        return jsonify(project=project, text=text, stamp=stamp, jira_url=jira_url,
                       history=notes.read_history(text), files=notes.list_files(folder),
                       messages=sent_messages(project))

    def sent_messages(project):
        """The card's newest messages to Claude, newest first: kind, text, sent, and status =
        "waiting for Claude" or "seen by Claude <day>" (the hooks mark a message seen).

        None = the card follows no work folder, so nothing is ever sent.
        [] = nothing sent yet, or the work folder can't be read right now.
        """
        work = notes.linked_folder(project)
        if not work:
            return None
        try:
            found = dashboard_inbox.read_all(work)
        except OSError as err:
            app.logger.warning("The dashboard messages in %s can't be read (%s): the card shows none", work, err)
            return []
        return [{"kind": m["kind"], "text": m["text"], "sent": m["sent"], "status": dashboard_inbox.status_text(m)}
                for m in reversed(found[-MESSAGES_SHOWN:])]

    def is_linked(folder):
        """True when this card follows a Claude work folder: Ask Claude then leaves the four synced fields alone."""
        text = (folder / notes.NOTE_FILE).read_text(encoding="utf-8-sig")
        return bool(notes.linked_folder(notes.parse_note(text)[0]))

    def chat_input():
        """Read {question, history: [{role, text}, ...]} sent by the page. Returns (question, history, error).

        The page keeps the chat (forgotten when you close it) and sends it all back each time.
        """
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        question = str(data.get("question") or "").strip()
        history = data.get("history") or []
        if not question:
            return question, history, "Type a question first."
        if not (isinstance(history, list) and all(
                isinstance(t, dict) and t.get("role") == ("user", "assistant")[i % 2] and isinstance(t.get("text"), str)
                for i, t in enumerate(history))):     # you, Claude, you, Claude, ...
            return question, history, "The chat got mixed up. Reload the page and ask again."
        return question, history, None

    @app.post("/api/ask")
    def api_ask_all():
        """The global Ask Claude page: a question about every open project. Answers only, no proposals."""
        question, history, error = chat_input()
        if error:
            return jsonify(error=error), 400
        context, skipped = claude_chat.all_projects_context(projects_folder, datetime.now(), text_limit)
        try:
            reply, _ = claude_chat.ask(claude(), model, context, history, question, system=claude_chat.ALL_SYSTEM)
        except claude_chat.ClaudeError as err:
            return jsonify(error=str(err)), 502
        return jsonify(reply=reply, skipped=skipped)

    @app.post("/api/projects/<project_id>/ask")
    def api_ask(project_id):
        """Ask Claude about one project. stamp = note.md's version when Claude read it (Approve checks it later)."""
        folder = folder_or_404(project_id)
        question, history, error = chat_input()
        if error:
            return jsonify(error=error), 400
        stamp = notes.note_stamp(folder)
        context, skipped = claude_chat.project_context(folder, datetime.now(), text_limit)
        try:
            reply, proposal = claude_chat.ask(claude(), model, context, history, question, can_propose=True,
                                              linked=is_linked(folder))
        except claude_chat.ClaudeError as err:
            return jsonify(error=str(err)), 502
        return jsonify(reply=reply, proposal=proposal, skipped=skipped, stamp=stamp)

    @app.post("/api/projects/<project_id>/apply")
    def api_apply(project_id):
        """Approve: save what Claude proposed. JSON {proposal, stamp} (stamp = from the /ask answer).

        If note.md changed since Claude read it, nothing is saved (409): the proposal may be out of date.
        """
        folder = folder_or_404(project_id)
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        try:
            proposal = claude_chat.clean_proposal(data.get("proposal"), is_linked(folder))     # never trust the page blindly
        except ValueError as err:
            return jsonify(error=str(err)), 400
        if not proposal:
            return jsonify(error="Nothing to apply."), 400
        stale = jsonify(error="This note changed since Claude read it. Ask Claude again."), 409
        if notes.note_stamp(folder) != data.get("stamp"):
            return stale

        now = datetime.now()
        text = (folder / notes.NOTE_FILE).read_text(encoding="utf-8-sig")
        text = notes.set_fields(text, {f["field"]: f["value"] for f in proposal["fields"]})
        if proposal["history_line"]:
            text = notes.add_history(text, proposal["history_line"], f"{now:%Y-%m-%d}", who="Claude (you approved)")
        session = None
        try:
            if proposal["session_note"]:      # written first; removed again if note.md can't be saved
                (folder / "sessions").mkdir(exist_ok=True)
                session = notes.free_name(folder / "sessions", f"{now:%Y-%m-%d}.md", now)
                notes.safe_write(session, proposal["session_note"] + "\n")
            stamp = notes.write_note(folder, text, data["stamp"], now)
        except (notes.StaleNote, OSError, ValueError) as err:
            if session:
                session.unlink(missing_ok=True)
            if isinstance(err, notes.StaleNote):
                return stale
            if isinstance(err, ValueError):
                return jsonify(error=str(err)), 400
            return jsonify(error=LOCKED.format("note.md")), 400
        return jsonify(stamp=stamp, session=session.name if session else None)

    @app.post("/api/projects/<project_id>/open-folder")
    def api_open_folder(project_id):
        """The page can't open folders on your disk, so Python asks the computer to do it."""
        folder = folder_or_404(project_id)
        try:
            open_in_file_manager(folder)
        except (OSError, subprocess.SubprocessError):
            return jsonify(error=f"Could not open {folder}. Open it yourself in File Explorer."), 400
        return jsonify(ok=True)

    def save(folder, make_text):
        """Shared by every save button. make_text(current note text) -> new note text.

        409 = note.md changed since the card opened; the page then offers
        "Save mine anyway" (sends force=true) or "Load the new version".
        """
        data = page_json(stamp=str)
        try:
            current = (folder / notes.NOTE_FILE).read_text(encoding="utf-8-sig")
            stamp = notes.write_note(folder, make_text(current), data["stamp"],
                                     datetime.now(), force=data.get("force", False))
        except notes.StaleNote:
            return jsonify(error="This note changed since you opened it."), 409
        except UnicodeDecodeError:
            return jsonify(error=notes.NOT_UTF8.format(notes.NOTE_FILE)), 400
        except ValueError as err:
            return jsonify(error=str(err)), 400
        except OSError:
            return jsonify(error=LOCKED.format(notes.NOTE_FILE)), 400
        return jsonify(stamp=stamp)

    @app.post("/api/projects/<project_id>/fields")
    def api_save_fields(project_id):
        """Save changes. JSON {fields: {name: value}, stamp}: only the fields that are sent are written
        (the page sends the boxes you changed), every other line of note.md stays as it is.

        On a linked card the sync fills in status / blocked_by / working_on / next from Claude's files:
        those four are never written from here, whatever the page sends.
        """
        folder = folder_or_404(project_id)
        sent = page_json(fields=dict)["fields"]
        fields = {k: str(sent[k]).strip() for k in FORM_FIELDS if k in sent}
        if "title" in fields and not fields["title"]:
            return jsonify(error="Give the project a name first."), 400
        for key, allowed in CHOICES.items():
            if key in fields and fields[key] not in allowed:
                return jsonify(error=f"{key} must be one of: {', '.join(allowed)}"), 400

        def with_fields(text):
            linked = notes.linked_folder(notes.parse_note(text)[0])
            return notes.set_fields(text, {k: v for k, v in fields.items()
                                           if not (linked and k in notes.SYNCED_FIELDS)})
        return save(folder, with_fields)

    @app.post("/api/projects/<project_id>/note")
    def api_save_note(project_id):
        folder = folder_or_404(project_id)
        new_text = page_json(text=str)["text"]
        return save(folder, lambda text: new_text)

    # ---------- the card's Note / Blocker / Unblock box ----------

    def write_message(folder, kind, text, now):
        """Put a card message into note.md: one History line by "you"; Blocker / Unblock also set / empty my_blocker.

        Returns (note text before, stamp before, stamp after, the work folder or ""). Raises Refused.
        It takes no stamp from the page: it reads note.md, adds only its own things and saves. If someone
        else saves note.md in that very moment (StaleNote), it reads their version and adds to that one.
        """
        change = {"blocker": {notes.MY_BLOCKER: text}, "unblock": {notes.MY_BLOCKER: ""}}.get(kind, {})
        for _ in range(MESSAGE_TRIES):
            before = notes.note_stamp(folder)
            old = (folder / notes.NOTE_FILE).read_text(encoding="utf-8-sig")
            fields = notes.parse_note(old)[0]
            if kind == "unblock" and not fields.get(notes.MY_BLOCKER):
                raise Refused(NO_BLOCKER)
            work = notes.linked_folder(fields)
            if work and not folder_is_there(work):      # checked before anything is saved
                app.logger.warning("Card message for %s not saved: its work folder %s is not there", folder.name, work)
                raise Refused(WORK_AWAY.format(work))
            # set_fields also adds an empty --- block to a note that has none, so the save is accepted
            new = notes.set_fields(notes.add_history(old, history_text(kind, text), f"{now:%Y-%m-%d}"), change)
            try:
                return old, before, notes.write_note(folder, new, before, now), work
            except notes.StaleNote:
                continue
        app.logger.warning("Card message for %s not saved: note.md changed %s times while saving", folder.name, MESSAGE_TRIES)
        raise Refused(BUSY_NOTE)

    def put_back(folder, old, stamp, now):
        """Undo our own save of note.md, when the message could not be left for Claude. False = not undone.

        Only while note.md is still exactly what we saved (stamp): someone else's newer save is never thrown away.
        """
        try:
            notes.write_file(folder / notes.NOTE_FILE, folder, old, stamp, now)
        except (notes.StaleNote, OSError, ValueError) as err:
            app.logger.error("note.md of %s could not be put back after a failed message (%s: %s): the card "
                             "has a line Claude did not get", folder.name, type(err).__name__, err)
            return False
        return True

    @app.post("/api/projects/<project_id>/message")
    def api_message(project_id):
        """The card's Note / Blocker / Unblock box. JSON {kind: "note" | "blocker" | "unblock", text}.

        Note = one History line by "you". Blocker = that + my_blocker gets the reason. Unblock = that +
        my_blocker is emptied (no words needed). status: and blocked_by: are never touched.
        A linked card (it follows a Claude work folder): the message is also left there for Claude.
        The card is saved first, then the message file. If the file can't be written, the card is put back
        as it was: all or nothing. If even that fails, the error says exactly what is where.
        Answers {stamp, before, sent}: note.md's stamp after and before, and whether Claude gets it.
        """
        folder = folder_or_404(project_id)
        data = page_json(kind=str, text=str)
        kind, text = data["kind"], " ".join(data["text"].split())      # one line, as dashboard_inbox.add makes it
        if kind not in dashboard_inbox.KINDS:
            raise PageSentOdd()
        if kind in dashboard_inbox.NEEDS_TEXT and not text:
            return jsonify(error=NO_WORDS), 400
        now = datetime.now()
        try:
            old, before, stamp, work = write_message(folder, kind, text, now)
        except Refused as err:
            return jsonify(error=str(err)), 400
        except UnicodeDecodeError:
            app.logger.warning("Card message for %s not saved: note.md is not UTF-8", project_id)
            return jsonify(error=notes.NOT_UTF8.format(notes.NOTE_FILE)), 400
        except ValueError as err:           # a broken character (half an emoji)
            app.logger.warning("Card message for %s not saved: %s", project_id, err)
            return jsonify(error=str(err)), 400
        except OSError as err:
            app.logger.warning("Card message for %s not saved: note.md could not be read or changed (%s)", project_id, err)
            return jsonify(error=LOCKED.format(notes.NOTE_FILE)), 400
        if work:
            try:
                dashboard_inbox.add(work, kind, text, now)
            except (OSError, ValueError) as err:
                why = getattr(err, "strerror", None) or str(err)
                app.logger.error("Card message for %s could not be left in %s (%s)", project_id, work, why)
                undone = put_back(folder, old, stamp, now)
                return jsonify(error=(NOT_SENT if undone else HALF_SENT).format(why)), 400
        return jsonify(stamp=stamp, before=before, sent=bool(work))

    # ---------- sessions\ and raw\ files ----------

    def file_or_404(project_id, dir, name):
        """(project folder, file path), or a 404 for a missing file or an unsafe name."""
        folder = folder_or_404(project_id)
        path = notes.file_path(folder, dir, name)
        if path is None or not path.is_file():
            abort(404)
        return folder, path

    def typed_name():
        """The name the user typed, made safe: "my notes?.md" -> "my_notes.md". None if nothing is left."""
        return secure_filename(str(page_json().get("name", ""))) or None

    @app.get("/api/projects/<project_id>/files/<dir>/<name>")
    def api_open_file(project_id, dir, name):
        _, path = file_or_404(project_id, dir, name)
        stamp = notes.file_stamp(path)
        return jsonify(stamp=stamp, size=path.stat().st_size, **notes.read_file(path))

    @app.get("/api/projects/<project_id>/files/<dir>/<name>/bytes")
    def api_file_bytes(project_id, dir, name):
        """The file itself, for the image preview. Images only: an .html file shown here could run scripts."""
        _, path = file_or_404(project_id, dir, name)
        if path.suffix.lower() not in notes.IMAGE_TYPES:
            abort(404)
        return send_file(path, max_age=0)

    @app.post("/api/projects/<project_id>/files/<dir>")
    def api_new_file(project_id, dir):
        folder = folder_or_404(project_id)
        if dir not in notes.FILE_DIRS:
            abort(404)
        name = typed_name()
        if not name:
            return jsonify(error="Use letters, numbers, - _ and . in the name."), 400
        try:
            notes.new_file(folder, dir, name)
        except FileExistsError:
            return jsonify(error=f"{dir}\\{name} already exists."), 400
        except OSError:
            return jsonify(error=LOCKED.format(f"{dir}\\{name}")), 400
        return jsonify(name=name)

    @app.post("/api/projects/<project_id>/files/<dir>/<name>")
    def api_save_file(project_id, dir, name):
        """Same 409 conflict answer as note.md saves."""
        folder, path = file_or_404(project_id, dir, name)
        if notes.read_file(path)["kind"] != "text":
            return jsonify(error="This file is not text, so it can't be edited here."), 400
        data = page_json(text=str, stamp=str)
        try:
            stamp = notes.write_file(path, folder, data["text"], data["stamp"],
                                     datetime.now(), force=data.get("force", False))
        except notes.StaleNote:
            return jsonify(error="This file changed since you opened it."), 409
        except ValueError as err:
            return jsonify(error=str(err)), 400
        except OSError:
            return jsonify(error=LOCKED.format(name)), 400
        return jsonify(stamp=stamp)

    @app.post("/api/projects/<project_id>/files/<dir>/<name>/rename")
    def api_rename_file(project_id, dir, name):
        _, path = file_or_404(project_id, dir, name)
        new_name = typed_name()
        if not new_name:
            return jsonify(error="Use letters, numbers, - _ and . in the name."), 400
        try:
            notes.rename_file(path, new_name)
        except FileExistsError:
            return jsonify(error=f"{dir}\\{new_name} already exists."), 400
        except OSError:
            return jsonify(error=LOCKED.format(name)), 400
        return jsonify(name=new_name)

    @app.post("/api/projects/<project_id>/files/<dir>/<name>/delete")
    def api_delete_file(project_id, dir, name):
        folder, path = file_or_404(project_id, dir, name)
        try:
            notes.archive_file(path, folder, datetime.now())
        except OSError:
            return jsonify(error=LOCKED.format(name)), 400
        return jsonify(ok=True)

    @app.post("/api/projects/<project_id>/upload")
    def api_upload(project_id):
        """Upload button, drag-and-drop and pasted screenshots. Always into raw\\, never overwrites."""
        folder = folder_or_404(project_id)
        now = datetime.now()
        try:
            names = [notes.save_upload(folder, secure_filename(f.filename or "") or "upload", f.read(), now)
                     for f in request.files.getlist("files")]
        except OSError:
            return jsonify(error=LOCKED.format(f"the {notes.UPLOAD_DIR} folder")), 400
        return jsonify(names=names)

    # ---------- Completed tab: ✓ Complete, Restore ----------

    def not_here():
        """Folders PROD_SCRIPTS must never be in."""
        return [f for f in (work_jira_folder, str(projects_folder)) if f]

    @app.get("/api/prod-folder")
    def api_prod_folder():
        """Where ✓ Complete would move a ticket folder: the tagged folder, or None (the page then asks once)."""
        found = prod_folder.find(user_home, not_here(), work_near, prod_roots)
        return jsonify(folder=str(found) if found else None, suggest=prod_folder.suggestion(user_home, work_near))

    @app.post("/api/projects/<project_id>/complete")
    def api_complete(project_id):
        """✓ Complete: move the card to _archive (the Completed tab). A ticket card also moves its work folder
        from work_jira to PROD_SCRIPTS first; both move or neither does. JSON {"prod_folder": path} = the
        one-time box's answer; without it the tagged folder is used.
        """
        folder = folder_or_404(project_id)
        project = notes.read_or_problem(folder)
        ready = ready_to_complete(project)
        if ready == "away":
            return jsonify(error=FOLDER_AWAY.format(project_id)), 400
        if ready == "unreadable":
            return jsonify(error=TICKET_UNREADABLE.format(project_id)), 400
        if not ready:
            return jsonify(error=NOT_CLOSED.format(project_id)), 400
        said = project_note.COMPLETED_CLOSED if ready == "closed" else notes.COMPLETED
        now = datetime.now()
        work = notes.linked_folder(project)
        moved = None
        if work:
            moved = move_ticket_out(project_id, Path(work), now)
            if not isinstance(moved, Path):
                return moved                                    # an error answer: nothing moved
        try:
            notes.archive_project(projects_folder, folder, now, said=said,
                                  fields={"prod_folder": str(moved)} if moved else None)
        except OSError as err:
            app.logger.error("Complete of %s failed: could not move its card", project_id, exc_info=err)
            if moved:
                stuck = move_back(project_id, moved, Path(work))
                if stuck:
                    return stuck
            return jsonify(error=move_problem(err)), 400
        return jsonify(ok=True)

    def move_ticket_out(project_id, work, now):
        """Move a ticket folder into PROD_SCRIPTS. Returns where it went, or an error answer (nothing moved)."""
        if not work_jira_folder or not project_note.same_folder(work.parent, Path(work_jira_folder)):
            app.logger.warning("Complete of %s refused: its folder %s is not in work_jira", project_id, work)
            return jsonify(error=NOT_IN_WORK_JIRA.format(project_id, work, work_jira_folder or "not set")), 400
        data = request.get_json(silent=True)
        typed = data.get("prod_folder") if isinstance(data, dict) else None
        if typed is None:
            prod = prod_folder.find(user_home, not_here(), work_near, prod_roots)
            if prod is None:
                app.logger.warning("Complete of %s waits: no folder for completed projects yet (asked)", project_id)
                return jsonify(error=NEED_FOLDER, need_folder=True,
                               suggest=prod_folder.suggestion(user_home, work_near)), 400
        elif not isinstance(typed, str):
            app.logger.warning("Complete of %s refused: the folder sent was not text", project_id)
            return jsonify(error=TODO_ODD), 400
        else:
            prod, why = prod_folder.check_choice(typed, user_home, not_here(), prod_roots)
            if prod is None:
                app.logger.warning("Complete of %s refused: bad folder for completed projects (%s)", project_id, why)
                return jsonify(error=why), 400
        try:
            prod_folder.make(prod)
        except OSError as err:
            app.logger.error("Complete of %s failed: could not make %s or its tag file", project_id, prod, exc_info=err)
            return jsonify(error=CANT_MAKE.format(prod, err.strerror or err)), 400
        try:
            return prod_folder.move_out(work, prod, now)
        except OSError as err:
            app.logger.error("Complete of %s failed: could not move %s to %s", project_id, work, prod, exc_info=err)
            return jsonify(error=folder_problem(err, work.name, work_jira_folder)), 400

    def move_back(project_id, moved, to):
        """Undo a ticket folder move after its card could not move. Returns an error answer if that fails too."""
        try:
            os.rename(moved, to)
            return None
        except OSError as err:
            app.logger.error("Could not put %s back to %s for %s", moved, to, project_id, exc_info=err)
            return jsonify(error=STUCK.format(project_id, moved)), 400

    @app.post("/api/completed/<project_id>/restore")
    def api_restore_project(project_id):
        """Restore: the ticket folder (if Complete moved one) goes back to work_jira under its own name, then the
        card comes back. Answers {id, warning?, still_closed?}: still_closed = its ticket has ## Closed.
        """
        archived = notes.find_archived(projects_folder, project_id)
        if archived is None:
            abort(404)
        try:
            card_fields = notes.parse_note((archived / notes.NOTE_FILE).read_text(encoding="utf-8-sig"))[0]
        except (OSError, UnicodeDecodeError) as err:
            app.logger.error("Restore of %s failed: could not read its card", project_id, exc_info=err)
            return jsonify(error=UNREADABLE.format(f"the card of {project_id}")), 400
        # The real path, once: a hand-edited line like "...\PROD_SCRIPTS\.." must not pass the checks below as
        # PROD_SCRIPTS and then move Documents (Windows tidies ".." away when it renames).
        stored = card_fields.get("prod_folder", "").strip()
        moved = Path(stored).resolve() if stored else None
        back, extra, warning = None, None, ""
        if moved:
            name = Path(notes.linked_folder(card_fields) or notes.archived_name(archived.name)).name
            extra = {"prod_folder": ""}
            if not moved.is_dir():          # you moved PROD_SCRIPTS since? Look in the one the tag file marks now
                now_at = prod_folder.find(user_home, not_here(), work_near, prod_roots)
                if now_at and (now_at / moved.name).is_dir():
                    app.logger.info("Restore of %s: %s not there, found it in %s", project_id, moved, now_at)
                    moved = now_at / moved.name
            if not moved.is_dir():          # nothing to move: only the card comes back, whatever else is true
                app.logger.warning("Restore of %s: its folder %s is gone, only the card comes back", project_id, moved)
                warning = FOLDER_MISSING.format(moved)
            elif (prod_folder.check_choice(moved, user_home, not_here(), prod_roots)[0] is None
                  or not prod_folder.has_tag(moved.parent)):           # only from a tagged folder, as Complete does
                app.logger.warning("Restore of %s refused: its prod_folder %s is outside the allowed places",
                                   project_id, moved)
                return jsonify(error=ODD_PROD_FOLDER.format(moved)), 400
            elif not work_jira_folder or not Path(work_jira_folder).is_dir():
                app.logger.warning("Restore of %s refused: work_jira folder not found", project_id)
                return jsonify(error=NO_WORK_JIRA.format(moved)), 400
            elif os.path.lexists(Path(work_jira_folder) / name):
                app.logger.warning("Restore of %s refused: %s already in work_jira", project_id, name)
                return jsonify(error=RESTORE_CLASH.format(name, work_jira_folder)), 400
            else:
                back = Path(work_jira_folder) / name
                try:
                    os.rename(moved, back)
                except OSError as err:
                    app.logger.error("Restore of %s failed: could not move %s back", project_id, moved, exc_info=err)
                    return jsonify(error=folder_problem(err, name, work_jira_folder)), 400
                if str(back) != notes.linked_folder(card_fields):     # work_jira moved since: point the card there
                    extra["folder"] = str(back)                        # (not always: note lines keep single spaces)
        try:
            new_id = notes.restore_project(projects_folder, archived, datetime.now(),
                                           name=notes.archived_name(archived.name), fields=extra)
        except OSError as err:
            app.logger.error("Restore of %s failed: could not move its card", project_id, exc_info=err)
            if back:
                stuck = move_back(project_id, back, moved)
                if stuck:
                    return stuck
            return jsonify(error=move_problem(err)), 400
        answer = {"id": new_id}
        if warning:
            answer["warning"] = warning
        if ready_to_complete(notes.read_or_problem(Path(projects_folder) / new_id)) == "closed":
            answer["still_closed"] = True
        return jsonify(answer)

    # ----- To do page -----

    @app.get("/api/todos")
    def api_todos():
        try:
            return jsonify(todos.listing(todos.read_todos(projects_folder)))
        except todos.Unreadable as err:
            return jsonify(error=str(err)), 400
        except OSError:
            return jsonify(error=UNREADABLE.format(todos.TODO_FILE)), 400

    def todo_change(change, **fields):
        """Shared by every To do change. Checks the JSON body has these fields (name=type), runs change(body)
        and answers with the list it saved, so the page just redraws. A bool is not an int here (True is 1 in Python).
        """
        data = request.get_json(silent=True)
        if not (isinstance(data, dict) and all(type(data.get(name)) is kind for name, kind in fields.items())):
            return jsonify(error=TODO_ODD), 400
        try:
            saved = change(data)
        except todos.ListChanged:
            return jsonify(error=todos.CHANGED), 409
        except (todos.Unreadable, todos.BadText) as err:
            return jsonify(error=str(err)), 400
        except OSError:
            return jsonify(error=LOCKED.format(todos.TODO_FILE)), 400
        return jsonify(todos.listing(saved))

    @app.post("/api/todos")
    def api_add_todo():
        return todo_change(lambda d: todos.add(projects_folder, d["text"]), text=str)

    @app.post("/api/todos/done")
    def api_todo_done():
        return todo_change(lambda d: todos.set_done(projects_folder, d["row"], d["text"], d["done"]),
                           **TODO_ROW, done=bool)

    @app.post("/api/todos/high")
    def api_todo_high():
        return todo_change(lambda d: todos.set_high(projects_folder, d["row"], d["text"], d["high"]),
                           **TODO_ROW, high=bool)

    @app.post("/api/todos/text")
    def api_todo_text():
        return todo_change(lambda d: todos.set_text(projects_folder, d["row"], d["text"], d["new_text"]),
                           **TODO_ROW, new_text=str)

    @app.post("/api/todos/delete")
    def api_delete_todo():
        return todo_change(lambda d: todos.delete(projects_folder, d["row"], d["text"]), **TODO_ROW)

    @app.post("/api/todos/clear-done")
    def api_clear_done():
        # texts = the done todos the page showed in "Delete N done todos for good?"
        return todo_change(lambda d: todos.clear_done(projects_folder, d["texts"]), texts=list)

    # ----- Slack button -----

    def slack_status():
        if slack is None:
            return {"state": "off", "message": slack_live.NO_USER_TOKEN, "mode": "",
                    **slack_inbox.Inbox().summary(datetime.now())}
        return slack.status()

    @app.get("/api/slack")
    def api_slack():
        """The page asks every few seconds. Never calls Slack: it reads what the Slack part already knows."""
        return jsonify(slack_status())

    @app.post("/api/slack/opened")
    def api_slack_opened():
        """You clicked a row (Slack opens it): it goes from the list at once."""
        data = request.get_json(silent=True) or {}
        channel, ts = data.get("channel"), data.get("ts")
        if not (isinstance(channel, str) and isinstance(ts, str) and channel and ts):
            return jsonify(error="channel and ts are needed"), 400
        if slack is not None:
            slack.inbox.opened(channel, ts)
        return jsonify(slack_status())

    return app


if __name__ == "__main__":
    create_app().run(port=PORT)
