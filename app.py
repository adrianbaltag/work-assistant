"""Work Assistant: a local web page over your project notes.

Run it:   python app.py      then open http://127.0.0.1:5050
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

import claude_chat
import notes
import slack_inbox
import slack_live

SETTINGS_FILE = notes.SETTINGS_FILE
load_settings = notes.load_settings     # lives in notes.py so helper scripts can read settings without Flask
PORT = 5050         # not 5000: macOS AirPlay Receiver uses that port
CHOICES = {"status": list(notes.STATUSES), "priority": ["critical", "high", "normal"]}
FORM_FIELDS = ["title", "status", "priority", "next", "blocked_by", "jira", "folder"]
UPLOAD_LIMIT_MB = 50
LOCKED = "Could not change {}. Is it open in another program (e.g. Excel)? Close it and try again."


def read_text_limit(value):
    """text_limit= as a number of characters (empty = the default). A bad value stops the app."""
    value = str(value).strip().replace("_", "")
    if not value:
        return claude_chat.TEXT_CAP
    if value.isdecimal() and int(value) > 0:
        return int(value)
    raise SystemExit(f'text_limit= in settings.ini must be a whole number of characters, like 200000 '
                     f'(no commas). It is "{value}".')


def read_jira_url(value):
    """jira_url= without a trailing /, or "" (Open in Jira off) when it isn't a web address."""
    value = value.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        return ""       # "jira.example.com" alone would open as a page of this app, not Jira
    return value


def open_in_file_manager(path):
    """Show a folder in Windows Explorer (Finder on a Mac). Tests swap this for a fake."""
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)], check=True)


def create_app(projects_folder=None, jira_url="", claude=claude_chat.make_client, model="", text_limit="",
               slack=None):
    """Build the Flask app. No folder given = a real run: read it (and jira_url, model, text_limit,
    the slack_ lines) from settings.ini, and start the Slack part.

    claude = a function that returns the Claude client; tests pass one that returns a fake.
    slack = the running Slack part (slack_live.Live); tests pass a fake, or none = "not connected".
    """
    slack_settings = None
    if projects_folder is None:
        settings = load_settings()
        projects_folder = settings["projects_folder"]
        jira_url = settings.get("jira_url", "")
        model = settings.get("model", "")
        text_limit = settings.get("text_limit", "")
        slack_settings = slack_inbox.slack_settings(settings)
    model = model.strip() or claude_chat.DEFAULT_MODEL
    text_limit = read_text_limit(text_limit)
    jira_url = read_jira_url(jira_url)
    if slack_settings is not None:      # last: a bad setting above stops the app with no Slack threads running
        slack = slack_live.start(slack_settings, slack_inbox.Inbox())
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = UPLOAD_LIMIT_MB * 1024 * 1024

    @app.before_request
    def same_site_only():
        """Refuse saves sent by other websites open in the same browser (they could upload or archive files)."""
        origin = request.headers.get("Origin")
        if request.method == "POST" and origin and urlparse(origin).netloc != request.host:
            return jsonify(error="Refused: this request came from another website."), 403

    @app.errorhandler(413)
    def too_big(_):
        return jsonify(error=f"Upload too big ({UPLOAD_LIMIT_MB} MB max at once)."), 413

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/api/projects")
    def api_projects():
        now = datetime.now()
        rows = notes.dashboard(notes.list_projects(projects_folder), now)
        for row in rows:
            del row["body"]
        return jsonify(today=now.strftime("%Y-%m-%d"), projects=rows)

    @app.post("/api/projects")
    def api_new_project():
        """+ New project. JSON {id, title, status}. The ID is cleaned ("my idea" -> "my_idea") and becomes the folder."""
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        project_id = secure_filename(str(data.get("id") or ""))     # "or": a JSON null must not become "None"
        status = str(data.get("status") or "active")
        if not project_id:
            return jsonify(error="Type a ticket ID or a short name (letters, digits, - or _)."), 400
        if status not in CHOICES["status"]:
            return jsonify(error=f"Unknown status: {status}."), 400
        try:
            notes.new_project(projects_folder, project_id, str(data.get("title") or ""), status)
        except FileExistsError:
            return jsonify(error=f'A folder named "{project_id}" already exists. Pick another name.'), 400
        except ValueError:
            return jsonify(error=f'"{project_id}" can\'t be used as a folder name. Pick another name.'), 400
        except OSError as err:
            return jsonify(error=f"Could not create the folder: {err}. Is the projects folder reachable?"), 400
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
        stamp = notes.note_stamp(folder)     # before reading: a change in between = a warning, not a lost edit
        project = notes.dashboard([notes.read_project(folder)], datetime.now())[0]
        text = (folder / notes.NOTE_FILE).read_text(encoding="utf-8-sig")
        return jsonify(project=project, text=text, stamp=stamp, jira_url=jira_url,
                       history=notes.read_history(text), files=notes.list_files(folder))

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
            reply, proposal = claude_chat.ask(claude(), model, context, history, question, can_propose=True)
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
            proposal = claude_chat.clean_proposal(data.get("proposal"))     # never trust the page blindly
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
        if proposal["session_note"]:      # written first; removed again if note.md can't be saved
            (folder / "sessions").mkdir(exist_ok=True)
            session = notes.free_name(folder / "sessions", f"{now:%Y-%m-%d}.md", now)
            session.write_text(proposal["session_note"] + "\n", encoding="utf-8")
        try:
            stamp = notes.write_note(folder, text, data["stamp"], now)
        except (notes.StaleNote, OSError) as err:
            if session:
                session.unlink()
            return stale if isinstance(err, notes.StaleNote) else (jsonify(error=LOCKED.format("note.md")), 400)
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
        data = request.get_json()
        current = (folder / notes.NOTE_FILE).read_text(encoding="utf-8-sig")
        try:
            stamp = notes.write_note(folder, make_text(current), data["stamp"],
                                     datetime.now(), force=data.get("force", False))
        except notes.StaleNote:
            return jsonify(error="This note changed since you opened it."), 409
        except ValueError as err:
            return jsonify(error=str(err)), 400
        return jsonify(stamp=stamp)

    @app.post("/api/projects/<project_id>/fields")
    def api_save_fields(project_id):
        folder = folder_or_404(project_id)
        fields = {k: str(request.get_json()["fields"].get(k, "")).strip() for k in FORM_FIELDS}
        if not fields["title"]:
            return jsonify(error="Give the project a name first."), 400
        for key, allowed in CHOICES.items():
            if fields[key] not in allowed:
                return jsonify(error=f"{key} must be one of: {', '.join(allowed)}"), 400
        return save(folder, lambda text: notes.set_fields(text, fields))

    @app.post("/api/projects/<project_id>/note")
    def api_save_note(project_id):
        folder = folder_or_404(project_id)
        return save(folder, lambda text: request.get_json()["text"])

    @app.post("/api/projects/<project_id>/history")
    def api_add_history(project_id):
        folder = folder_or_404(project_id)
        said = request.get_json()["text"].strip()
        if not said:
            return jsonify(error="Write something first."), 400
        today = datetime.now().strftime("%Y-%m-%d")
        # set_fields(..., {}) adds an empty --- block if the note has none, so the save is accepted
        return save(folder, lambda text: notes.set_fields(notes.add_history(text, said, today), {}))

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
        return secure_filename(str(request.get_json().get("name", ""))) or None

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
        return jsonify(name=name)

    @app.post("/api/projects/<project_id>/files/<dir>/<name>")
    def api_save_file(project_id, dir, name):
        """Same 409 conflict answer as note.md saves."""
        folder, path = file_or_404(project_id, dir, name)
        if notes.read_file(path)["kind"] != "text":
            return jsonify(error="This file is not text, so it can't be edited here."), 400
        data = request.get_json()
        try:
            stamp = notes.write_file(path, folder, data["text"], data["stamp"],
                                     datetime.now(), force=data.get("force", False))
        except notes.StaleNote:
            return jsonify(error="This file changed since you opened it."), 409
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
        names = [notes.save_upload(folder, secure_filename(f.filename or "") or "upload", f.read(), now)
                 for f in request.files.getlist("files")]
        return jsonify(names=names)

    # ---------- Archive page: Mark done & archive, Restore ----------

    @app.post("/api/projects/<project_id>/archive")
    def api_archive_project(project_id):
        folder = folder_or_404(project_id)
        try:
            notes.archive_project(projects_folder, folder, datetime.now())
        except OSError:
            return jsonify(error=LOCKED.format("the project folder")), 400
        return jsonify(ok=True)

    @app.get("/api/archive")
    def api_archive():
        return jsonify(notes.list_archive(projects_folder))

    @app.post("/api/archive/projects/<project_id>/restore")
    def api_restore_project(project_id):
        archived = notes.find_archived(projects_folder, project_id)
        if archived is None:
            abort(404)
        try:
            new_id = notes.restore_project(projects_folder, archived, datetime.now())
        except OSError:
            return jsonify(error=LOCKED.format("the project folder")), 400
        return jsonify(id=new_id)

    @app.post("/api/archive/files/restore")
    def api_restore_file():
        """JSON body {project, dir, name}: dir can be "" (old note.md copies), which a URL can't hold."""
        data = request.get_json()
        folder = folder_or_404(str(data.get("project", "")))
        dir, name = str(data.get("dir", "")), str(data.get("name", ""))
        path = notes.archived_file_path(folder, dir, name)
        if path is None or not path.is_file():
            abort(404)
        try:
            where = notes.restore_file(folder, dir, name, datetime.now())
        except OSError:
            return jsonify(error=LOCKED.format(path.name)), 400
        return jsonify(where=where)

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
