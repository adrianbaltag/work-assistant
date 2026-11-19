"""Check your setup before starting the app: Python, packages, settings.ini, the Claude login, Slack.

Run it:   python check_setup.py
One line per check; each problem says what to do. Tokens are never printed.
It sends Claude one tiny message (well under a cent) and asks Slack who you are.
It saves one small file in Claude Code's own folder: ticket-flow-home.txt, the path of this folder, so the
ticket-flow plugin's hooks can find it. Nothing else is changed.
"""
import json
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
POINTER = "ticket-flow-home.txt"       # tells the ticket-flow hooks where this folder is (ticket-flow/scripts/run_hook.py reads it)
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


def check_settings(path):
    """Returns (lines, the settings dict or None when settings.ini can't be read, the slack_ settings).

    The checks themselves are app.validate_settings (the app's start-up uses the same ones);
    this only gives each finding its [ OK ] / [FAIL] mark. A bad slack_ line is reported there;
    the Slack checks then run with the defaults.
    """
    import app             # here, not at the top: check_packages must run before Flask is imported
    settings, slack_cfg, findings = app.validate_settings(path)
    marks = {"ok": OK, "bad": BAD, "warn": WARN, "skip": SKIP}
    return [(marks[f.level], f.text) for f in findings], settings, slack_cfg


def claude_folder(env):
    """Claude Code's own folder: ~/.claude, unless CLAUDE_CONFIG_DIR says another one."""
    other = (env.get("CLAUDE_CONFIG_DIR") or "").strip()
    return Path(other) if other else Path.home() / ".claude"


def check_ticket_flow(claude, here=HERE):
    """The ticket-flow plugin (optional). Saves where this folder is, for the plugin's hooks; then, when the
    plugin is installed: is it this folder's version, and are the old pasted hooks still in settings.json?

    claude = Claude Code's own folder. Only the pointer file is written; settings.json is only read.
    """
    claude, here = Path(claude), Path(here).resolve()
    if not claude.is_dir():
        return [(SKIP, f"ticket-flow plugin: Claude Code's folder ({claude}) was not found, so the plugin "
                       "was not checked (optional).")]
    lines = []
    try:
        (claude / POINTER).write_text(f"{here}\n", encoding="utf-8")
    except OSError as err:
        lines.append((WARN, f"ticket-flow plugin: could not save {claude / POINTER} ({err.strerror or err}). "
                            "Its hooks may not find this folder. Check that you may write in that folder."))
    try:
        plugins = json.loads((claude / "plugins" / "installed_plugins.json").read_text(encoding="utf-8-sig"))["plugins"]
        found = {name: [entry.get("version", "") for entry in entries]
                 for name, entries in plugins.items() if name.startswith("ticket-flow@")}
        wanted = json.loads((here / "ticket-flow" / ".claude-plugin" / "plugin.json")
                            .read_text(encoding="utf-8-sig"))["version"]
    except FileNotFoundError:
        found = {}                       # no plugin was ever installed (or this folder has no plugin): same answer
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return lines + [(SKIP, "ticket-flow plugin: could not tell if it is installed (Claude Code's plugin list "
                               "can't be read). In Claude Code, type /plugin to see it.")]
    if not found:
        return lines + [(SKIP, 'ticket-flow plugin: not installed (optional). README, "Sync with work_jira", '
                               "shows how.")]
    name, versions = sorted(found.items())[0]
    old = [v for v in versions if v != wanted]
    if old:
        lines.append((WARN, f"ticket-flow plugin: the installed one is version {old[0] or 'unknown'}, this folder "
                            f"has {wanted}. Run:  claude plugin update {name}  and then start Claude again."))
    else:
        lines.append((OK, f"ticket-flow plugin: installed, version {wanted}"))
    events = pasted_hook_events(claude / "settings.json")
    if events:
        lines.append((WARN, f"Old hooks: {claude / 'settings.json'} still runs work_jira_hooks.py itself (under "
                            f"{', '.join(events)}). The ticket-flow plugin runs these now, so each one runs twice. "
                            'Open that file and delete those entries under "hooks". Keep the "permissions" part.'))
    return lines


def pasted_hook_events(settings_file):
    """The hook events in Claude Code's settings.json that run work_jira_hooks.py (pasted in before the plugin
    existed). [] when there are none, or the file can't be read. The file is never changed."""
    try:
        hooks = json.loads(Path(settings_file).read_text(encoding="utf-8-sig"))["hooks"]
        return [event for event, groups in hooks.items() if "work_jira_hooks.py" in json.dumps(groups)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


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


def main(env=os.environ, settings_path=None, claude=None):
    """Run every check, print one line each, return 0 (all good) or 1 (problems).

    claude = Claude Code's own folder (tests pass a made-up one)."""
    lines = check_python() + check_packages()
    if BAD not in [mark for mark, _ in lines]:      # the rest needs the packages
        import app
        import claude_chat
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient
        found, settings, slack_cfg = check_settings(settings_path or app.SETTINGS_FILE)
        lines += found
        lines += check_ticket_flow(claude or claude_folder(env))
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
