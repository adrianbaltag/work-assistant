"""Work Assistant: a local web page over your project notes.

Run it:   python app.py      then open http://127.0.0.1:5050
"""
import configparser
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

import notes

HERE = Path(__file__).parent
SETTINGS_FILE = HERE / "settings.ini"
PORT = 5050         # not 5000: macOS AirPlay Receiver uses that port
CHOICES = {"status": ["active", "pending", "idea"], "priority": ["critical", "high", "normal"]}
FORM_FIELDS = ["title", "status", "priority", "next", "blocked_by", "jira", "folder"]
UPLOAD_LIMIT_MB = 50
LOCKED = "Could not change {}. Is it open in another program (e.g. Excel)? Close it and try again."


def load_settings(path=SETTINGS_FILE):
    """Read key=value lines from settings.ini into a dict.

    The file has no [section] header, so we add one before parsing.
    Raw mode: backslashes and % in paths/URLs are kept as typed.
    """
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"{path} not found. Copy settings.ini.example to "
                         "settings.ini and set projects_folder= to your notes folder.")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string("[settings]\n" + path.read_text(encoding="utf-8-sig"))
    return dict(parser["settings"])


def open_in_file_manager(path):
    """Show a folder in Windows Explorer (Finder on a Mac). Tests swap this for a fake."""
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)], check=True)


def create_app(projects_folder=None, jira_url=""):
    """Build the Flask app. No folder given = read it (and jira_url) from settings.ini."""
    if projects_folder is None:
        settings = load_settings()
        projects_folder = settings["projects_folder"]
        jira_url = settings.get("jira_url", "")
    jira_url = jira_url.strip().rstrip("/")
    if not jira_url.startswith(("http://", "https://")):
        jira_url = ""       # "jira.example.com" alone would open as a page of this app, not Jira
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
        data = request.get_json(silent=True) or {}
        project_id = secure_filename(str(data.get("id", "")))
        status = str(data.get("status", "active"))
        if not project_id:
            return jsonify(error="Type a ticket ID or a short name (letters, digits, - or _)."), 400
        if status not in CHOICES["status"]:
            return jsonify(error=f"Unknown status: {status}."), 400
        try:
            notes.new_project(projects_folder, project_id, str(data.get("title", "")), status)
        except (FileExistsError, ValueError):
            return jsonify(error=f'A folder named "{project_id}" already exists. Pick another name.'), 400
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

    return app


if __name__ == "__main__":
    create_app().run(port=PORT)
