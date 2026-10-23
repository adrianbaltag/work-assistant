"""check_setup.py: one line per check, a fix for each problem, never a token. Fakes, so no network.

All IDs and tokens here are made up. Never put real ones in this public repo.
"""
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from slack_sdk.errors import SlackApiError

import check_setup
import claude_chat
import slack_inbox

OK, BAD, WARN, SKIP = check_setup.OK, check_setup.BAD, check_setup.WARN, check_setup.SKIP


def marks(lines):
    return [mark for mark, _ in lines]


def text(lines):
    return "\n".join(words for _, words in lines)


# ----- Python and packages -----

def test_python_3_10_is_fine():
    assert marks(check_setup.check_python((3, 10, 11))) == [OK]


def test_python_3_9_is_too_old():
    lines = check_setup.check_python((3, 9, 18))
    assert marks(lines) == [BAD] and "3.10" in text(lines)


def test_packages_match_requirements(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("flask==3.1.3\nanthropic==1.15.0\n", encoding="utf-8")
    versions = {"flask": "3.1.3", "anthropic": "1.15.0"}
    assert marks(check_setup.check_packages(reqs, versions.get)) == [OK]


def test_missing_or_wrong_package_says_pip_install(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("flask==3.1.3\nanthropic==1.15.0\nslack_sdk==3.45.0\n", encoding="utf-8")
    versions = {"flask": "3.0.0", "anthropic": "1.15.0"}      # slack_sdk missing
    lines = check_setup.check_packages(reqs, versions.get)
    assert marks(lines) == [BAD]
    assert "flask 3.0.0 (needs 3.1.3)" in text(lines) and "slack_sdk not installed" in text(lines)
    assert "pip install -r requirements.txt" in text(lines)


# ----- settings.ini -----

def write_settings(tmp_path, body):
    path = tmp_path / "settings.ini"
    path.write_text(body, encoding="utf-8")
    return path


def test_good_settings(tmp_path):
    (tmp_path / "projects").mkdir()
    (tmp_path / "work_jira").mkdir()
    path = write_settings(tmp_path, f"projects_folder={tmp_path / 'projects'}\njira_url=https://jira.example.com\n"
                                    f"work_jira_folder={tmp_path / 'work_jira'}\n")
    lines, settings, _ = check_setup.check_settings(path)
    assert set(marks(lines)) == {OK} and settings["jira_url"] == "https://jira.example.com"


def test_no_settings_file(tmp_path):
    lines, settings, _ = check_setup.check_settings(tmp_path / "settings.ini")
    assert marks(lines) == [BAD] and "settings.ini.example" in text(lines) and settings is None


def test_projects_folder_missing_or_not_set(tmp_path):
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, f"projects_folder={tmp_path / 'nope'}\n"))
    assert BAD in marks(lines) and "does not exist" in text(lines)
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, "jira_url=https://jira.example.com\n"))
    assert BAD in marks(lines) and "projects_folder=" in text(lines)


def test_bad_values_use_the_apps_own_words(tmp_path):
    (tmp_path / "p").mkdir()
    path = write_settings(tmp_path, f"projects_folder={tmp_path / 'p'}\ntext_limit=200,000\nslack_mode=fast\n")
    lines, _, _ = check_setup.check_settings(path)
    assert marks(lines).count(BAD) == 2
    assert "whole number of characters" in text(lines) and "instant or backup" in text(lines)


def test_jira_url_that_is_not_a_web_address_is_a_warning(tmp_path):
    (tmp_path / "p").mkdir()
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, f"projects_folder={tmp_path / 'p'}\n"
                                                                   "jira_url=jira.example.com\n"))
    assert WARN in marks(lines) and "Open in Jira" in text(lines)



def test_work_jira_folder_blank_is_skipped_not_a_problem(tmp_path):
    (tmp_path / "p").mkdir()
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, f"projects_folder={tmp_path / 'p'}\n"
                                                                   "work_jira_folder=\n"))
    assert marks(lines) == [OK, OK, SKIP] and "optional" in text(lines)


def test_work_jira_folder_that_does_not_exist(tmp_path):
    (tmp_path / "p").mkdir()
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, f"projects_folder={tmp_path / 'p'}\n"
                                                                   f"work_jira_folder={tmp_path / 'nope'}\n"))
    assert BAD in marks(lines) and "work_jira_folder=" in text(lines) and "does not exist" in text(lines)


def test_work_jira_folder_counts_project_folders_only(tmp_path):
    (tmp_path / "p").mkdir()
    work = tmp_path / "work_jira"
    for name in ["DEMO-1", "DEMO-2", "_templates", ".claude"]:
        (work / name).mkdir(parents=True)
    (work / "CLAUDE.md").write_text("rules", encoding="utf-8")
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, f"projects_folder={tmp_path / 'p'}\n"
                                                                   f"work_jira_folder={work}\n"))
    assert set(marks(lines)) == {OK} and f"work_jira_folder: {work} (2 project folders)" in text(lines)

# ----- Claude -----

class FakeClaude:
    def __init__(self, error=None):
        self.error, self.sent = error, []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.sent.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(stop_reason="end_turn", content=[])


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
HOME = {"ANTHROPIC_API_KEY": "sk-ant-made-up"}
WORK = {"ANTHROPIC_AUTH_TOKEN": "made-up", "ANTHROPIC_BASE_URL": "https://gateway.example.com"}


def test_claude_answers_with_the_settings_model():
    fake = FakeClaude()
    lines = check_setup.check_claude(HOME, {"model": "claude-haiku-5-5"}, lambda: fake)
    assert marks(lines) == [OK, OK] and "claude-haiku-5-5" in text(lines)
    assert fake.sent[0]["model"] == "claude-haiku-5-5" and fake.sent[0]["max_tokens"] <= 100


def test_claude_default_model_and_work_gateway_shown():
    fake = FakeClaude()
    lines = check_setup.check_claude(WORK, {}, lambda: fake)
    assert "gateway.example.com" in text(lines) and fake.sent[0]["model"] == claude_chat.DEFAULT_MODEL
    assert "made-up" not in text(lines)


def test_no_claude_login_is_a_problem_and_nothing_is_sent():
    fake = FakeClaude()
    lines = check_setup.check_claude({}, {}, lambda: fake)
    assert marks(lines) == [BAD] and "ANTHROPIC_API_KEY" in text(lines) and not fake.sent


def test_work_token_without_gateway_address():
    lines = check_setup.check_claude({"ANTHROPIC_AUTH_TOKEN": "made-up"}, {}, FakeClaude)
    assert marks(lines) == [BAD] and "ANTHROPIC_BASE_URL" in text(lines)


def test_claude_error_in_plain_english():
    error = anthropic.NotFoundError("boom", response=httpx2.Response(404, request=REQUEST), body=None)
    lines = check_setup.check_claude(HOME, {"model": "claude-x"}, lambda: FakeClaude(error))
    assert marks(lines) == [OK, BAD] and claude_chat.plain_error(error, "claude-x") in text(lines)


# ----- Slack -----

SLACK_DEFAULTS = slack_inbox.slack_settings({})
ALL_SCOPES = ",".join(check_setup.SLACK_SCOPES)
USER = {"SLACK_USER_TOKEN": "xoxp-made-up"}
BOTH = {**USER, "SLACK_APP_TOKEN": "xapp-made-up"}


def slack_error(code):
    return SlackApiError(f"The request failed: {code}", {"ok": False, "error": code})


class Answer(dict):
    """Like slack_sdk's SlackResponse: answer["user"], plus the HTTP headers."""

    def __init__(self, data, headers):
        super().__init__(data)
        self.headers = headers


class FakeWeb:
    """Stands in for slack_sdk's WebClient."""

    def __init__(self, scopes=ALL_SCOPES, error=None, header="X-OAuth-Scopes"):
        self.scopes, self.error, self.header, self.tokens = scopes, error, header, []

    def __call__(self, token):          # the web= factory: token -> client
        self.tokens.append(token)
        return self

    def auth_test(self):
        if self.error:
            raise self.error
        return Answer({"user": "adrian", "team": "Test Team"},
                      {} if self.scopes is None else {self.header: self.scopes})


def check_user(env, settings=SLACK_DEFAULTS, web=None):
    return check_setup.check_slack_user(env, settings, web or FakeWeb())


def test_slack_not_set_up_is_skipped_not_a_problem():
    lines, ok = check_user({})
    assert marks(lines) == [SKIP] and "optional" in text(lines) and not ok


def test_slack_login_shows_who_and_where_but_not_the_token():
    web = FakeWeb()
    lines, ok = check_user(USER, web=web)
    assert set(marks(lines)) == {OK} and ok
    assert "adrian" in text(lines) and "Test Team" in text(lines) and "xoxp-made-up" not in text(lines)
    assert web.tokens == ["xoxp-made-up"]


@pytest.mark.parametrize("token, words", [("xoxb-made-up", "Bot"), ("xapp-made-up", "SLACK_APP_TOKEN"),
                                          ("made-up", "xoxp-")])
def test_wrong_kind_of_token_is_named(token, words):
    web = FakeWeb()
    lines, ok = check_user({"SLACK_USER_TOKEN": token}, web=web)
    assert marks(lines) == [BAD] and words in text(lines) and not ok and not web.tokens
    assert token not in text(lines)


def test_missing_permissions_are_named():
    scopes = ", ".join(s for s in check_setup.SLACK_SCOPES if s not in ("search:read", "users:read"))
    lines, ok = check_user(USER, web=FakeWeb(scopes=scopes, header="x-oauth-scopes"))
    assert BAD in marks(lines) and "missing permissions: search:read, users:read." in text(lines)
    assert not ok


def test_groups_permission_only_needed_when_groups_count():
    scopes = ",".join(s for s in check_setup.SLACK_SCOPES if s != "usergroups:read")
    lines, ok = check_user(USER, {**SLACK_DEFAULTS, "count_groups": False}, FakeWeb(scopes=scopes))
    assert set(marks(lines)) == {OK} and ok
    lines, ok = check_user(USER, SLACK_DEFAULTS, FakeWeb(scopes=scopes))
    assert BAD in marks(lines) and "usergroups:read" in text(lines)


def test_permissions_unknown_is_a_warning():
    lines, ok = check_user(USER, web=FakeWeb(scopes=None))
    assert WARN in marks(lines) and ok


def test_slack_login_error_in_plain_english():
    lines, ok = check_user(USER, web=FakeWeb(error=slack_error("invalid_auth")))
    assert marks(lines) == [BAD] and slack_inbox.plain_error(slack_error("invalid_auth")) in text(lines)
    assert not ok


def test_slack_unreachable_in_plain_english():
    lines, _ = check_user(USER, web=FakeWeb(error=OSError("no network")))
    assert marks(lines) == [BAD] and "internet" in text(lines)


class FakeSocket:
    """Stands in for slack_sdk's SocketModeClient: connects after `after` checks, or never."""

    def __init__(self, after=0, error=None):
        self.after, self.error, self.closed, self.tokens = after, error, False, []

    def __call__(self, app_token):      # the socket= factory
        self.tokens.append(app_token)
        return self

    def connect(self):
        if self.error:
            raise self.error

    def is_connected(self):
        self.after -= 1
        return self.after < 0

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def check_app(env, socket, settings=SLACK_DEFAULTS, user_ok=True):
    clock = Clock()
    return check_setup.check_slack_app(env, settings, user_ok, socket, clock, clock.sleep)


def test_instant_connection_opens_and_is_closed_again():
    socket = FakeSocket(after=3)
    lines = check_app(BOTH, socket)
    assert marks(lines) == [OK] and socket.closed and socket.tokens == ["xapp-made-up"]
    assert "xapp-made-up" not in text(lines)


def test_instant_connection_blocked_says_use_backup():
    socket = FakeSocket(after=10 ** 6)
    lines = check_app(BOTH, socket)
    assert marks(lines) == [BAD] and "slack_mode=backup" in text(lines) and socket.closed


def test_app_token_refused():
    socket = FakeSocket(error=slack_error("invalid_auth"))
    lines = check_app(BOTH, socket)
    assert marks(lines) == [BAD] and "SLACK_APP_TOKEN" in text(lines) and socket.closed


def test_no_app_token_means_backup_mode_warning():
    socket = FakeSocket()
    lines = check_app(USER, socket)
    assert marks(lines) == [WARN] and "30 seconds" in text(lines) and not socket.tokens


def test_app_token_of_the_wrong_kind():
    socket = FakeSocket()
    lines = check_app({**USER, "SLACK_APP_TOKEN": "xoxp-made-up"}, socket)
    assert marks(lines) == [BAD] and "xapp-" in text(lines) and not socket.tokens


def test_backup_mode_or_no_slack_login_skips_the_app_token():
    assert marks(check_app(BOTH, FakeSocket(), {**SLACK_DEFAULTS, "mode": "backup"})) == [SKIP]
    assert marks(check_app(BOTH, FakeSocket(), user_ok=False)) == [SKIP]


def test_manifest_asks_for_exactly_the_permissions_checked():
    import json
    manifest = json.loads((check_setup.HERE / "slack-app-manifest.json").read_text(encoding="utf-8"))
    assert sorted(manifest["oauth_config"]["scopes"]["user"]) == sorted(check_setup.SLACK_SCOPES)
    assert manifest["settings"]["socket_mode_enabled"] is True


def test_main_prints_every_line_and_counts_the_problems(tmp_path, capsys):
    (tmp_path / "p").mkdir()
    path = write_settings(tmp_path, f"projects_folder={tmp_path / 'p'}\n")
    assert check_setup.main(env={}, settings_path=path) == 1        # no logins: nothing goes to the network
    out = capsys.readouterr().out
    assert "[FAIL] No Claude login" in out and "[SKIP] Slack: SLACK_USER_TOKEN" in out
    assert out.strip().endswith("1 problem to fix (the [FAIL] lines). Run this again after.")


# ----- A command pasted where the token should go (read -s shows nothing, so it's easy to do) -----

PASTED = "read -s ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY"


@pytest.mark.parametrize("env", [{"ANTHROPIC_API_KEY": PASTED},
                                 {"ANTHROPIC_AUTH_TOKEN": PASTED, "ANTHROPIC_BASE_URL": "https://gateway.example.com"}])
def test_claude_token_with_spaces_was_pasted_wrong(env):
    fake = FakeClaude()
    lines = check_setup.check_claude(env, {}, lambda: fake)
    assert marks(lines) == [BAD] and "paste only the" in text(lines) and not fake.sent
    assert PASTED not in text(lines)


def test_claude_key_that_does_not_look_like_a_key():
    fake = FakeClaude()
    lines = check_setup.check_claude({"ANTHROPIC_API_KEY": "made-up"}, {}, lambda: fake)
    assert marks(lines) == [BAD] and "sk-ant-" in text(lines) and not fake.sent


@pytest.mark.parametrize("name", ["SLACK_USER_TOKEN", "SLACK_APP_TOKEN"])
def test_slack_token_with_spaces_was_pasted_wrong(name):
    env = {**BOTH, name: "read -s X && export X"}
    lines, _ = check_user(env)
    lines += check_app(env, FakeSocket())
    assert "paste only the" in text(lines) and "read -s" not in text(lines)


# ----- Review fixes -----

def test_unreadable_settings_line_is_shown_with_its_line_number(tmp_path):
    lines, settings, _ = check_setup.check_settings(write_settings(tmp_path, "jira_url=x\nmy projects folder\n"))
    assert marks(lines) == [BAD] and settings is None
    assert "line 2" in text(lines) and "my projects folder" in text(lines)


def test_key_written_twice_is_shown_with_its_line_number(tmp_path):
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, "jira_url=a\njira_url=b\n"))
    assert marks(lines) == [BAD] and "line 2" in text(lines) and "jira_url" in text(lines)


def test_projects_are_counted_the_way_the_app_counts_them(tmp_path):
    folder = tmp_path / "p"
    for name, has_note in (("DEMO-1", True), ("_templates", True), ("scratch", False), ("_archive", True)):
        (folder / name).mkdir(parents=True)
        if has_note:
            (folder / name / "note.md").write_text("---\ntitle: x\n---\n", encoding="utf-8")
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, f"projects_folder={folder}\n"))
    assert "(2 projects)" in text(lines)


def test_projects_folder_that_cannot_be_read(tmp_path, monkeypatch):
    import notes
    (tmp_path / "p").mkdir()

    def refuse(folder):
        raise PermissionError("Access is denied")
    monkeypatch.setattr(notes, "list_projects", refuse)
    lines, _, _ = check_setup.check_settings(write_settings(tmp_path, f"projects_folder={tmp_path / 'p'}\n"))
    assert BAD in marks(lines) and "can't be read" in text(lines)


def test_bad_slack_settings_fall_back_to_the_defaults_for_the_slack_checks(tmp_path):
    (tmp_path / "p").mkdir()
    _, _, slack_cfg = check_setup.check_settings(write_settings(tmp_path, f"projects_folder={tmp_path / 'p'}\n"
                                                                          "slack_mode=fast\n"))
    assert slack_cfg == SLACK_DEFAULTS


def test_instant_test_skipped_while_the_app_runs():
    socket = FakeSocket()
    clock = Clock()
    lines = check_setup.check_slack_app(BOTH, SLACK_DEFAULTS, True, socket, clock, clock.sleep, app_running=True)
    assert marks(lines) == [SKIP] and "close the app" in text(lines) and not socket.tokens


@pytest.mark.parametrize("code, refused", [("invalid_token", True), ("account_inactive", True),
                                           ("ratelimited", False)])
def test_app_token_refused_the_same_way_the_app_decides(code, refused):
    import slack_live
    lines = check_app(BOTH, FakeSocket(error=slack_error(code)))
    assert marks(lines) == [BAD] and (slack_live.BAD_APP_TOKEN in text(lines)) == refused


@pytest.mark.parametrize("env", [{"ANTHROPIC_AUTH_TOKEN": "  "}, {"ANTHROPIC_API_KEY": " "}])
def test_claude_token_of_only_spaces_counts_as_not_set(env):
    lines = check_setup.check_claude(env, {}, FakeClaude)
    assert marks(lines) == [BAD] and "No Claude login found" in text(lines)


def test_gateway_address_without_https():
    lines = check_setup.check_claude({**WORK, "ANTHROPIC_BASE_URL": "gateway.example.com"}, {}, FakeClaude)
    assert marks(lines) == [BAD] and "https://" in text(lines)
