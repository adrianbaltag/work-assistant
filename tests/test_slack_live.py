"""The background part of the Slack button: doorbell, catch-up, read check, backup rounds, call gate.

No threads and no real waiting: tests call tick() by hand, jobs run at once, and a fake clock moves
only when the code "sleeps". A fake Slack and a fake doorbell, so no network. IDs are made up.
"""
import http.client
from datetime import timedelta
from types import SimpleNamespace

import pytest
from slack_sdk.errors import SlackApiError

import slack_inbox
import slack_live
from test_slack_inbox import DM_MIKE, ME, MIKE, NOW, OPS, FakeSlack, error, found, msg, ts

TOKENS = {"SLACK_USER_TOKEN": "xoxp-test", "SLACK_APP_TOKEN": "xapp-test"}


class Clock:
    """Seconds since the test started. sleep() just moves it on."""

    def __init__(self):
        self.t = 0.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(round(seconds, 3))
        self.t += seconds


class FakeSocket:
    """Stands in for slack_sdk's SocketModeClient (the doorbell)."""

    def __init__(self, log):
        self.socket_mode_request_listeners = []
        self.up = False
        self.connects = 0
        self.closed = False
        self.fail = None        # exception connect() raises
        self.log = log          # shared with the fake Slack, to see what happened first

    def connect(self):
        if self.fail:
            raise self.fail
        self.connects += 1
        self.up = True

    def is_connected(self):
        return self.up

    def send_socket_mode_response(self, response):
        self.log.append(("ack", {"envelope_id": response.envelope_id}))

    def close(self):
        self.closed = True
        self.up = False

    def push(self, event, kind="events_api"):
        req = SimpleNamespace(type=kind, envelope_id="E1", payload={"event": event})
        for listener in self.socket_mode_request_listeners:
            listener(self, req)


class Rig:
    """One Live with its fakes. jobs run at once unless hold=True (then they wait in self.jobs)."""

    def __init__(self, settings=None, env=TOKENS, hold=False):
        self.slack = FakeSlack()
        self.slack.dm_pages = [[{"id": DM_MIKE, "is_im": True, "user": MIKE}]]
        self.clock = Clock()
        self.sockets = []
        self.jobs = []
        self.hold = hold
        self.inbox = slack_inbox.Inbox()
        self.live = slack_live.Live(
            slack_inbox.slack_settings(settings or {}), self.inbox, env=env,
            web=self.make_web, socket=self.make_socket,
            clock=self.clock, now=lambda: NOW + timedelta(seconds=self.clock.t), sleep=self.clock.sleep,
            background=self.background)

    def make_web(self, token):
        assert token == "xoxp-test"
        return self.slack

    def make_socket(self, app_token):
        assert app_token == "xapp-test"
        self.sockets.append(FakeSocket(self.slack.calls))
        return self.sockets[-1]

    def background(self, job):
        self.jobs.append(job) if self.hold else job()

    def run_jobs(self):
        while self.jobs:
            self.jobs.pop(0)()

    @property
    def socket(self):
        return self.sockets[-1]

    def later(self, seconds):
        self.clock.t += seconds
        self.live.tick()

    def status(self):
        return self.live.status()



def mentions(rig):
    return [r["text"] for r in rig.status()["mentions"]]


# ---------- Gate: every Slack call waits its turn ----------

class Response(dict):
    """What a SlackApiError carries: the answer, and the HTTP headers."""

    def __init__(self, headers, **answer):
        super().__init__(answer)
        self.headers = headers


def test_gate_spaces_calls_for_all_jobs_together():
    clock, slack = Clock(), FakeSlack()
    gate = slack_live.Gate(slack, per_minute=40, clock=clock, sleep=clock.sleep)
    gate.auth_test()
    gate.conversations_info(channel=OPS)
    gate.users_info(user=MIKE)
    assert clock.slept == [1.5, 1.5]
    assert slack.names() == ["auth_test", "conversations_info", "users_info"]


def test_gate_does_not_wait_when_calls_are_far_apart():
    clock, slack = Clock(), FakeSlack()
    gate = slack_live.Gate(slack, per_minute=40, clock=clock, sleep=clock.sleep)
    gate.auth_test()
    clock.t += 60
    gate.auth_test()
    assert clock.slept == []


def test_gate_waits_as_long_as_slack_asks_then_tries_again():
    clock, slack = Clock(), FakeSlack()
    gate = slack_live.Gate(slack, per_minute=40, clock=clock, sleep=clock.sleep)
    real = slack.auth_test
    answers = [SlackApiError("ratelimited", Response({"Retry-After": "7"}, ok=False, error="ratelimited"))]

    def auth_test():
        if answers:
            raise answers.pop()
        return real()
    slack.auth_test = auth_test
    assert gate.auth_test()["user_id"] == ME
    assert clock.slept == [7]


def test_gate_gives_up_when_slack_keeps_saying_too_many():
    clock, slack = Clock(), FakeSlack()
    gate = slack_live.Gate(slack, per_minute=40, clock=clock, sleep=clock.sleep)
    slack.fail["auth_test"] = SlackApiError("ratelimited", Response({}, ok=False, error="ratelimited"))
    with pytest.raises(SlackApiError):
        gate.auth_test()
    assert slack.names().count("auth_test") == slack_live.TRIES


def test_gate_passes_other_errors_straight_on():
    clock, slack = Clock(), FakeSlack()
    gate = slack_live.Gate(slack, per_minute=40, clock=clock, sleep=clock.sleep)
    slack.fail["auth_test"] = error("invalid_auth")
    with pytest.raises(SlackApiError):
        gate.auth_test()
    assert slack.names() == ["auth_test"]


# ---------- starting ----------

def test_no_user_token_means_not_connected_and_no_slack_calls():
    rig = Rig(env={"SLACK_APP_TOKEN": "xapp-test"})
    rig.live.tick()
    s = rig.status()
    assert s["state"] == "off" and "SLACK_USER_TOKEN" in s["message"]
    assert rig.slack.calls == [] and rig.sockets == []


def test_instant_start_connects_the_doorbell_then_catches_up():
    rig = Rig()
    rig.slack.channels[DM_MIKE]["unread_count_display"] = 1
    rig.slack.history[DM_MIKE] = [msg("sent while the app was off", minutes_ago=30)]
    rig.live.tick()
    assert rig.socket.connects == 1
    assert "users_conversations" in rig.slack.names() and "search_messages" in rig.slack.names()
    s = rig.status()
    assert s["state"] == "connected" and s["mode"] == "instant" and s["message"] == ""
    assert s["count"] == 1


def test_status_says_checking_before_the_first_tick():
    assert Rig().status()["state"] == "checking"


def test_status_says_checking_while_the_catch_up_runs():
    rig = Rig(hold=True)
    rig.live.tick()
    assert rig.status()["state"] == "checking"
    rig.run_jobs()
    assert rig.status()["state"] == "connected"


def test_a_running_catch_up_is_never_started_twice():
    rig = Rig(hold=True)
    rig.live.tick()
    rig.later(2)
    rig.later(2)
    assert len(rig.jobs) == 1


def test_start_runs_only_once(monkeypatch):
    monkeypatch.setattr(slack_live, "_live", None)
    loops = []
    first = slack_live.start(slack_inbox.slack_settings({}), slack_inbox.Inbox(), env={}, background=loops.append)
    second = slack_live.start(slack_inbox.slack_settings({}), slack_inbox.Inbox(), env={}, background=loops.append)
    assert first is second


def test_start_runs_the_ticker_in_the_background_when_there_is_a_token(monkeypatch):
    monkeypatch.setattr(slack_live, "_live", None)
    loops = []
    slack_live.start(slack_inbox.slack_settings({}), slack_inbox.Inbox(), env=TOKENS,
                     web=lambda token: FakeSlack(), socket=lambda app_token: FakeSocket([]),
                     background=loops.append)
    assert len(loops) == 1


def test_start_runs_nothing_without_a_token(monkeypatch):
    monkeypatch.setattr(slack_live, "_live", None)
    loops = []
    slack_live.start(slack_inbox.slack_settings({}), slack_inbox.Inbox(), env={}, background=loops.append)
    assert loops == []


# ---------- the doorbell ----------

def test_pushed_message_is_acknowledged_first_then_becomes_a_row():
    rig = Rig()
    rig.live.tick()
    rig.slack.calls.clear()
    rig.socket.push({**msg(f"<@{ME}> check site 1234"), "channel": OPS, "channel_type": "channel"})
    assert rig.slack.calls[0] == ("ack", {"envelope_id": "E1"})
    assert mentions(rig) == ["@Adrian check site 1234"]


def test_pushes_that_are_not_messages_are_ignored():
    rig = Rig()
    rig.live.tick()
    rig.slack.calls.clear()
    rig.socket.push({"type": "reaction_added"})
    rig.socket.push({}, kind="slash_commands")
    assert rig.slack.calls == [("ack", {"envelope_id": "E1"})]
    assert rig.status()["count"] == 0


def test_a_failing_push_shows_a_message_and_keeps_listening():
    rig = Rig()
    rig.live.tick()
    rig.slack.fail["users_info"] = OSError("network down")
    rig.socket.push({**msg(f"<@{ME}> one"), "channel": OPS, "channel_type": "channel"})
    assert "internet" in rig.status()["message"]
    del rig.slack.fail["users_info"]
    rig.socket.push({**msg(f"<@{ME}> two"), "channel": OPS, "channel_type": "channel"})
    assert mentions(rig) == ["@Adrian two"]


def test_doorbell_down_says_reconnecting_and_catches_up_when_back():
    rig = Rig()
    rig.live.tick()
    rig.socket.up = False
    rig.later(2)
    assert rig.status()["state"] == "reconnecting"
    rig.slack.channels[DM_MIKE]["unread_count_display"] = 1
    rig.slack.history[DM_MIKE] = [msg("sent while the lid was closed", minutes_ago=1)]
    rig.socket.up = True        # slack_sdk reconnects on its own
    rig.later(2)
    assert rig.status()["state"] == "connected"
    assert rig.slack.names().count("users_conversations") == 2
    assert rig.status()["count"] == 1
    assert rig.socket.connects == 1     # never a second doorbell


def test_doorbell_that_cannot_connect_is_tried_again():
    rig = Rig()
    doorbell = FakeSocket(rig.slack.calls)
    doorbell.fail = OSError("no network")
    rig.live.socket_factory = lambda app_token: doorbell
    rig.live.tick()
    assert rig.status()["state"] == "reconnecting"
    doorbell.fail = None
    rig.later(2)
    assert rig.status()["state"] == "connected" and doorbell.connects == 1


def test_a_wrong_app_token_names_slack_app_token():
    rig = Rig()
    doorbell = FakeSocket(rig.slack.calls)
    doorbell.fail = error("invalid_auth")
    rig.live.socket_factory = lambda app_token: doorbell
    rig.live.tick()
    s = rig.status()
    assert s["state"] == "error" and "SLACK_APP_TOKEN" in s["message"]


# ---------- the read check ----------

def test_read_check_runs_every_10_seconds_only_while_there_are_rows():
    rig = Rig()
    rig.live.tick()
    rig.slack.calls.clear()
    rig.later(10)
    assert "conversations_info" not in rig.slack.names()        # nothing unread: no asking
    rig.slack.channels[OPS]["last_read"] = ts(60)
    rig.socket.push({**msg(f"<@{ME}> look"), "channel": OPS, "channel_type": "channel"})
    rig.slack.calls.clear()
    rig.later(10)
    assert rig.slack.names() == ["conversations_info"]
    rig.slack.calls.clear()
    rig.later(5)
    assert rig.slack.calls == []                                 # too soon
    rig.slack.channels[OPS]["last_read"] = ts(0)                 # you read it in Slack
    rig.later(5)
    assert rig.status()["count"] == 0


# ---------- backup mode ----------

def test_backup_mode_from_settings_uses_no_doorbell():
    rig = Rig({"slack_mode": "backup"})
    rig.live.tick()
    s = rig.status()
    assert rig.sockets == [] and s["mode"] == "backup" and s["state"] == "connected"
    assert "slack_mode=backup" in s["message"] and "30 seconds" in s["message"] and "DMs" in s["message"]


def test_no_app_token_means_backup_mode_and_says_why():
    rig = Rig(env={"SLACK_USER_TOKEN": "xoxp-test"})
    rig.live.tick()
    s = rig.status()
    assert rig.sockets == [] and s["mode"] == "backup" and "SLACK_APP_TOKEN" in s["message"]


def test_backup_rounds_find_new_mentions_every_poll_seconds():
    rig = Rig({"slack_mode": "backup"})
    rig.live.tick()                             # first: the full catch-up
    rig.slack.channels[OPS]["last_read"] = ts(60)
    rig.slack.matches[f"<@{ME}>"] = [found(msg(f"<@{ME}> new", minutes_ago=-0.2))]
    rig.slack.calls.clear()
    rig.later(20)
    assert "search_messages" not in rig.slack.names()          # too soon
    rig.later(10)
    assert mentions(rig) == ["@Adrian new"]


def test_backup_rounds_check_the_next_batch_of_dms_each_time():
    rig = Rig({"slack_mode": "backup"})
    many = [f"D0{n:03}" for n in range(25)]
    rig.slack.dm_pages = [[{"id": d, "is_im": True, "user": MIKE} for d in many]]
    for d in many:
        rig.slack.channels[d] = {"id": d, "is_im": True, "user": MIKE, "last_read": ts(60), "unread_count_display": 0}
    rig.live.tick()                             # full catch-up asks about all 25
    batch = slack_live.dm_batch(30, 5)
    assert batch == 10

    def asked():
        got = [kw["channel"] for name, kw in rig.slack.calls if name == "conversations_info" and kw["channel"] in many]
        rig.slack.calls.clear()
        return got
    asked()
    rig.later(30)
    assert asked() == many[0:10]
    rig.later(30)
    assert asked() == many[10:20]
    rig.later(30)
    assert asked() == many[20:25]
    rig.later(30)
    assert asked() == many[0:10]                # round and round


def test_dm_batch_never_drops_below_one():
    assert slack_live.dm_batch(5, 8) == 1


def test_backup_round_finds_a_new_dm():
    rig = Rig({"slack_mode": "backup"})
    rig.live.tick()
    rig.slack.channels[DM_MIKE]["unread_count_display"] = 1
    rig.slack.history[DM_MIKE] = [msg("you there?", minutes_ago=-0.2)]
    rig.later(30)
    assert [r["text"] for r in rig.status()["dms"]] == ["you there?"]


# ---------- errors ----------

def test_a_failed_backup_round_still_waits_for_the_next_one():
    rig = Rig({"slack_mode": "backup"})
    rig.live.tick()
    rig.slack.fail["search_messages"] = OSError("no network")
    rig.later(30)
    rig.slack.calls.clear()
    rig.later(2)
    rig.later(2)
    assert rig.slack.calls == []


def test_the_stop_reason_stays_even_if_another_call_then_works():
    rig = Rig()
    rig.live.tick()
    rig.slack.fail["conversations_info"] = error("token_revoked")
    rig.socket.push({**msg(f"<@{ME}> hi"), "channel": OPS, "channel_type": "channel"})
    rig.live.client.auth_test()             # another thread's call that still worked
    assert "removed" in rig.status()["message"]


def test_any_refusal_of_the_app_token_names_slack_app_token():
    rig = Rig()
    doorbell = FakeSocket(rig.slack.calls)
    doorbell.fail = error("not_allowed_token_type")
    rig.live.socket_factory = lambda app_token: doorbell
    rig.live.tick()
    assert rig.status()["state"] == "error" and "SLACK_APP_TOKEN" in rig.status()["message"]


def test_a_broken_answer_from_the_network_is_tried_again():
    rig = Rig()
    rig.slack.fail["auth_test"] = http.client.IncompleteRead(b"")
    rig.live.tick()
    assert rig.status()["state"] == "reconnecting"
    del rig.slack.fail["auth_test"]
    rig.later(2)
    assert rig.status()["state"] == "connected"


def test_read_check_keeps_running_while_the_doorbell_is_down():
    rig = Rig()
    rig.live.tick()
    rig.slack.channels[OPS]["last_read"] = ts(60)
    rig.socket.push({**msg(f"<@{ME}> look"), "channel": OPS, "channel_type": "channel"})
    rig.socket.up = False
    rig.slack.channels[OPS]["last_read"] = ts(0)        # read on the phone meanwhile
    rig.later(10)
    assert rig.status()["count"] == 0

def test_wrong_user_token_stops_with_a_plain_message_and_no_more_calls():
    rig = Rig()
    rig.slack.fail["auth_test"] = error("invalid_auth")
    rig.live.tick()
    s = rig.status()
    assert s["state"] == "error" and "SLACK_USER_TOKEN" in s["message"]
    rig.slack.calls.clear()
    rig.later(30)
    assert rig.slack.calls == [] and rig.sockets == []


def test_token_removed_while_running_stops_and_closes_the_doorbell():
    rig = Rig()
    rig.live.tick()
    rig.slack.fail["conversations_info"] = error("token_revoked")
    rig.socket.push({**msg(f"<@{ME}> hi"), "channel": OPS, "channel_type": "channel"})
    rig.later(10)
    assert rig.status()["state"] == "error" and rig.socket.closed


def test_no_network_at_start_retries_on_the_next_tick():
    rig = Rig()
    rig.slack.fail["auth_test"] = OSError("no network")
    rig.live.tick()
    s = rig.status()
    assert s["state"] == "reconnecting" and "internet" in s["message"]
    del rig.slack.fail["auth_test"]
    rig.later(2)
    s = rig.status()
    assert s["state"] == "connected" and s["message"] == ""


def test_a_failed_catch_up_is_tried_again():
    rig = Rig()
    rig.slack.fail["users_conversations"] = OSError("no network")
    rig.live.tick()
    assert rig.status()["state"] == "reconnecting"
    del rig.slack.fail["users_conversations"]
    rig.later(2)
    assert rig.slack.names().count("users_conversations") == 2
    assert rig.status()["state"] == "connected"


def test_an_unexpected_bug_stops_the_slack_part_and_says_so():
    rig = Rig()
    rig.slack.fail["auth_test"] = KeyError("user_id")
    rig.live.tick()
    s = rig.status()
    assert s["state"] == "error" and "restart" in s["message"].lower()
