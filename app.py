"""Work Assistant: a local web page over your project notes.

Run it:   python app.py      then open http://127.0.0.1:5050
"""
import configparser
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

import notes

HERE = Path(__file__).parent
SETTINGS_FILE = HERE / "settings.ini"
PORT = 5050         # not 5000: macOS AirPlay Receiver uses that port
CHOICES = {"status": ["active", "pending", "idea"], "priority": ["critical", "high", "normal"]}
FORM_FIELDS = ["title", "status", "priority", "next", "blocked_by", "jira", "folder"]


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


def create_app(projects_folder=None):
    """Build the Flask app. No folder given = read it from settings.ini."""
    if projects_folder is None:
        projects_folder = load_settings()["projects_folder"]
    app = Flask(__name__)

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

    def folder_or_404(project_id):
        folder = notes.find_project(projects_folder, project_id)
        if folder is None:
            abort(404)
        return folder

    @app.get("/api/projects/<project_id>")
    def api_project(project_id):
        """Everything the project card needs. stamp = note.md's version, sent back on save."""
        folder = folder_or_404(project_id)
        project = notes.dashboard([notes.read_project(folder)], datetime.now())[0]
        text = (folder / notes.NOTE_FILE).read_text(encoding="utf-8-sig")
        return jsonify(project=project, text=text, stamp=notes.note_stamp(folder),
                       history=notes.read_history(text))

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
        return save(folder, lambda text: notes.add_history(text, said, today))

    return app


if __name__ == "__main__":
    create_app().run(port=PORT)
