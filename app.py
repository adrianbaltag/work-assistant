"""Work Assistant: a local web page over your project notes.

Run it:   python app.py      then open http://127.0.0.1:5050
"""
import configparser
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template

import notes

HERE = Path(__file__).parent
SETTINGS_FILE = HERE / "settings.ini"
PORT = 5050         # not 5000: macOS AirPlay Receiver uses that port


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

    return app


if __name__ == "__main__":
    create_app().run(port=PORT)
