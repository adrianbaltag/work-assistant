"""Check your setup before starting the app: Python, packages, settings.ini, the Claude login, Slack.

Run it:   python check_setup.py
One line per check; each problem says what to do. Tokens are never printed.
It sends Claude one tiny message (well under a cent) and asks Slack who you are. Nothing is changed.
"""
import configparser
import os
import sys
import time
from importlib import metadata
from pathlib import Path
from socket import create_connection
from urllib.parse import urlparse

HERE = Path(__file__).parent
# Plain text marks, not emoji: an old Windows console (or output saved to a file) can't always show emoji.
OK, BAD, WARN, SKIP = "[ OK ]", "[FAIL]", "[WARN]", "[SKIP]"
PING = "Reply with the word OK."
PING_TOKENS = 64            # Sonnet 5.5 always thinks a little first; any answer at all proves the login


def installed(name):
    """A package's installed version, or None."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def pasted_wrong(name, value):
    """A [FAIL] line when a token has spaces in it: read -s shows nothing, so a command gets pasted instead."""
    if len(value.split()) > 1:
        return [(BAD, f"{name} has spaces in it, so something else was pasted instead of the token "
                      f"(maybe the command itself). Set {name} again and paste only the token.")]
    return []


def check_python(version=sys.version_info):
    shown = ".".join(str(n) for n in version[:3])
    if tuple(version[:2]) >= (3, 10):
        return [(OK, f"Python {shown}")]
    return [(BAD, f"Python {shown} is too old. Install Python 3.10 or newer, then make the .venv again.")]


def check_packages(requirements=HERE / "requirements.txt", version=installed):
    wrong = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        name, _, wanted = line.strip().partition("==")
        if not wanted:
            continue
        found = version(name)
        if found is None:
            wrong.append(f"{name} not installed")
        elif found != wanted:
            wrong.append(f"{name} {found} (needs {wanted})")
    if not wrong:
        return [(OK, "Packages match requirements.txt")]
    return [(BAD, "Packages: " + ", ".join(wrong) + ". With the .venv on, run: pip install -r requirements.txt")]


def unreadable(path, err):
    """A configparser error in plain English, with the line as the person wrote it."""
    rows = Path(path).read_text(encoding="utf-8-sig").splitlines()
    line = lambda n: rows[n - 2] if 2 <= n <= len(rows) + 1 else ""     # n - 2: load_settings adds "[settings]" on top
    if isinstance(err, configparser.DuplicateOptionError):
        return f"settings.ini has {err.option}= twice (again on line {err.lineno - 1}). Keep one of them."
    if isinstance(err, configparser.ParsingError) and err.errors:
        n = err.errors[0][0]
        return (f'settings.ini line {n - 1} is not "key=value": {line(n)}  Fix or delete that line '
                "(a line starting with # is a note).")
    return f"settings.ini can't be read: {err}".splitlines()[0]


def check_settings(path):
    """Returns (lines, the settings dict or None when settings.ini can't be read, the slack_ settings).

    A bad slack_ line is reported here; the Slack checks then run with the defaults.
    """
    import app             # here, not at the top: check_packages must run before Flask is imported
    import notes
    import slack_inbox
    slack_cfg = slack_inbox.slack_settings({})
    try:
        settings = app.load_settings(path)
    except SystemExit as err:
        return [(BAD, str(err))], None, slack_cfg
    except configparser.Error as err:
        return [(BAD, unreadable(path, err))], None, slack_cfg
    lines = [(OK, f"settings.ini found ({path})")]
    folder = settings.get("projects_folder", "").strip()
    if not folder:
        lines.append((BAD, "projects_folder= is missing in settings.ini. Set it to your notes folder."))
    elif not Path(folder).is_dir():
        lines.append((BAD, f"projects_folder= {folder} does not exist. Fix the path in settings.ini."))
    else:
        try:
            count = len(notes.list_projects(folder))
        except OSError as err:
            lines.append((BAD, f"projects_folder= {folder} can't be read ({err.strerror or err}). "
                               "Check the path, the VPN (for a network drive) and that you may open it."))
        else:
            lines.append((OK, f"projects_folder: {folder} ({count} projects)"))
    try:
        app.read_text_limit(settings.get("text_limit", ""))
    except SystemExit as err:
        lines.append((BAD, str(err)))
    try:
        slack_cfg = slack_inbox.slack_settings(settings)
    except SystemExit as err:
        lines.append((BAD, str(err)))
    if settings.get("jira_url", "").strip() and not app.read_jira_url(settings["jira_url"]):
        lines.append((WARN, "jira_url= must start with https:// (or http://). Until then, Open in Jira is off."))
    return lines, settings, slack_cfg


def check_claude(env, settings, make_client):
    """make_client = claude_chat.make_client (tests pass a fake). Reads the login from env itself."""
    import anthropic
    import claude_chat
    model = settings.get("model", "").strip() or claude_chat.DEFAULT_MODEL
    env = {name: env.get(name, "").strip() for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY",
                                                         "ANTHROPIC_BASE_URL")}
    for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        if problem := pasted_wrong(name, env[name]):
            return problem
    if env["ANTHROPIC_AUTH_TOKEN"]:
        gateway = env["ANTHROPIC_BASE_URL"]
        if not gateway:
            return [(BAD, "ANTHROPIC_AUTH_TOKEN is set but ANTHROPIC_BASE_URL is not. At work, set both "
                          "(the gateway address goes in ANTHROPIC_BASE_URL).")]
        if not gateway.startswith(("https://", "http://")):
            return [(BAD, f"ANTHROPIC_BASE_URL must be a full web address starting with https:// "
                          f'(it is "{gateway}").')]
        login = f"Claude login: ANTHROPIC_AUTH_TOKEN, through {urlparse(gateway).netloc}"
    elif env["ANTHROPIC_API_KEY"]:
        if not env["ANTHROPIC_API_KEY"].startswith("sk-ant-"):
            return [(BAD, "ANTHROPIC_API_KEY does not look like a Claude API key (those start with sk-ant-). "
                          "Set it again and paste only the key.")]
        login = "Claude login: ANTHROPIC_API_KEY"
    else:
        return [(BAD, "No Claude login found. Set ANTHROPIC_API_KEY (home) or ANTHROPIC_AUTH_TOKEN + "
                      "ANTHROPIC_BASE_URL (work) in this window. The README shows how.")]
    lines = [(OK, login)]
    try:
        make_client().messages.create(model=model, max_tokens=PING_TOKENS,
                                      messages=[{"role": "user", "content": PING}])
    except claude_chat.ClaudeError as err:
        lines.append((BAD, str(err)))
    except anthropic.APIError as err:
        lines.append((BAD, claude_chat.plain_error(err, model)))
    else:
        lines.append((OK, f"Claude answered (model {model})"))
    return lines


# Every user permission the Slack button uses (slack-app-manifest.json asks for exactly these).
SLACK_SCOPES = ["channels:history", "channels:read", "groups:history", "groups:read", "im:history", "im:read",
                "mpim:history", "mpim:read", "search:read", "users:read", "usergroups:read"]
GROUPS_SCOPE = "usergroups:read"        # only needed while slack_count_groups=yes
CONNECT_SECONDS = 10


def check_slack_user(env, slack_cfg, web):
    """Returns (lines, True when the login works). web = token -> WebClient (tests pass a fake)."""
    import slack_inbox
    from slack_sdk.errors import SlackApiError
    token = env.get("SLACK_USER_TOKEN", "").strip()
    if not token:
        return [(SKIP, "Slack: SLACK_USER_TOKEN is not set, so the Slack button is off. Slack is optional; "
                       "the README shows how to connect it.")], False
    if problem := pasted_wrong("SLACK_USER_TOKEN", token):
        return problem, False
    if not token.startswith("xoxp-"):
        if token.startswith("xoxb-"):
            why = "is a Bot token (xoxb-…)"
        elif token.startswith("xapp-"):
            why = "is the app-level token (xapp-…), which goes in SLACK_APP_TOKEN"
        else:
            why = "does not start with xoxp-"
        return [(BAD, f"SLACK_USER_TOKEN {why}. Use the User OAuth Token (xoxp-…) from your Slack app's "
                      "OAuth & Permissions page.")], False
    try:
        login = web(token).auth_test()
    except (SlackApiError, OSError) as err:
        return [(BAD, slack_inbox.plain_error(err))], False
    lines = [(OK, f'Slack login: {login["user"]} in workspace "{login["team"]}"')]
    headers = {name.lower(): value for name, value in login.headers.items()}
    if "x-oauth-scopes" not in headers:
        lines.append((WARN, "Slack did not say which permissions your token has, so they weren't checked."))
        return lines, True
    has = {scope.strip() for scope in headers["x-oauth-scopes"].split(",")}
    needed = [s for s in SLACK_SCOPES if slack_cfg["count_groups"] or s != GROUPS_SCOPE]
    missing = [s for s in needed if s not in has]
    if missing:
        lines.append((BAD, "Your Slack app is missing permissions: " + ", ".join(missing) + ". Add them under "
                           "OAuth & Permissions > User Token Scopes, click Reinstall, then set the new "
                           "SLACK_USER_TOKEN."))
        return lines, False
    lines.append((OK, "Slack permissions: all there"))
    return lines, True


def app_is_running(port):
    """True when something (the app, most likely) already answers on this port."""
    try:
        create_connection(("127.0.0.1", port), timeout=0.5).close()
        return True
    except OSError:
        return False


def check_slack_app(env, slack_cfg, user_ok, socket, clock, sleep, app_running=False):
    """Opens the instant connection for up to CONNECT_SECONDS, then closes it. socket = app token -> client.

    Skipped while the app runs: Slack would hand some of its messages to this test connection instead.
    """
    import slack_inbox
    import slack_live
    from slack_sdk.errors import SlackApiError
    if not user_ok:
        return [(SKIP, "Slack instant connection: needs a working SLACK_USER_TOKEN first.")]
    if slack_cfg["mode"] == "backup":
        return [(SKIP, "Slack instant connection: not used (slack_mode=backup in settings.ini).")]
    if app_running:
        return [(SKIP, "Slack instant connection: not tested because the app is running. To test it, "
                       "close the app (Ctrl+C in its window) and run this check again.")]
    token = env.get("SLACK_APP_TOKEN", "").strip()
    if not token:
        return [(WARN, f"SLACK_APP_TOKEN is not set, so the app checks Slack every {slack_cfg['poll_seconds']} "
                       "seconds instead of instantly (new DMs can take a few minutes). Set it for instant.")]
    if problem := pasted_wrong("SLACK_APP_TOKEN", token):
        return problem
    if not token.startswith("xapp-"):
        return [(BAD, "SLACK_APP_TOKEN must be the app-level token (xapp-…) from your Slack app's "
                      "Basic Information page.")]
    client = socket(token)
    try:
        client.connect()            # asks Slack for the connection address first: a bad token fails here
        end = clock() + CONNECT_SECONDS
        while clock() < end:
            if client.is_connected():
                return [(OK, "Slack instant connection: works")]
            sleep(0.5)
    except SlackApiError as err:
        if err.response.get("error") == "ratelimited":
            return [(BAD, slack_inbox.plain_error(err))]
        return [(BAD, slack_live.BAD_APP_TOKEN)]        # the same rule the app uses
    except OSError as err:
        return [(BAD, slack_inbox.plain_error(err))]
    finally:
        client.close()
    return [(BAD, f"SLACK_APP_TOKEN is fine, but the instant connection did not open in {CONNECT_SECONDS} "
                  "seconds. The network may block it: put slack_mode=backup in settings.ini (or try again).")]


def main(env=os.environ, settings_path=None):
    """Run every check, print one line each, return 0 (all good) or 1 (problems)."""
    lines = check_python() + check_packages()
    if BAD not in [mark for mark, _ in lines]:      # the rest needs the packages
        import app
        import claude_chat
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient
        found, settings, slack_cfg = check_settings(settings_path or app.SETTINGS_FILE)
        lines += found
        lines += check_claude(env, settings or {}, claude_chat.make_client)
        found, user_ok = check_slack_user(env, slack_cfg, lambda token: WebClient(token=token))
        lines += found
        lines += check_slack_app(env, slack_cfg, user_ok, lambda token: SocketModeClient(app_token=token),
                                 time.monotonic, time.sleep, app_is_running(app.PORT))
    for mark, words in lines:
        print(f"{mark} {words}")
    problems = [mark for mark, _ in lines].count(BAD)
    print()
    print("All good. You can start the app." if not problems else
          f"{problems} problem{'s' if problems > 1 else ''} to fix (the [FAIL] lines). Run this again after.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
