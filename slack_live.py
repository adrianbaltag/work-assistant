"""The background part of the Slack button: keeps it up to date while the app runs.

Instant mode: Slack pushes each new message over the "doorbell" (Socket Mode) within a second.
Backup mode: no doorbell; every slack_poll_seconds the app looks for new mentions and a batch of DMs.
Both: a full catch-up on start and after every lost connection, and a read check while anything is
unread: every 10 seconds, or less often when many conversations have rows (it uses at most half the calls). The rules (what glows, what a row shows) live in slack_inbox.py.

Every Slack call goes through one Gate, so all of this together stays under Slack's limits.
"""
import http.client
import os
import threading
import time
from datetime import datetime, timedelta

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse

import slack_inbox

TICK_SECONDS = 2            # how often the ticker looks at the doorbell and the clocks
READ_CHECK_SECONDS = 10     # "did you read it in Slack?" while anything is unread
CALLS_PER_MINUTE = 40       # all jobs together; Slack allows about 50 a minute
READ_CALL_SECONDS = 2 * 60 / CALLS_PER_MINUTE   # read check: one call per 3 s at most = half the calls
TRIES = 3                   # a call Slack refuses with "too many calls" is tried this often
READ_RESERVE = 5            # calls per backup round kept free for the read check
SEARCH_MARGIN = 120         # backup searches look this many seconds before the last round (search is a bit slow)
NO_USER_TOKEN = ("Slack is not connected. To connect it, set SLACK_USER_TOKEN (the User OAuth Token, "
                 "xoxp-…) in this Terminal, then restart the app.")
BAD_APP_TOKEN = ("Slack refused SLACK_APP_TOKEN (the app-level token, xapp-…). Check it and restart the app, "
                 "or put slack_mode=backup in settings.ini.")
STOPPED = "The Slack part stopped because of an unexpected error ({}). Restart the app."


def in_thread(job):
    threading.Thread(target=job, daemon=True).start()      # daemon: it ends when the app ends


def dm_batch(poll_seconds, used):
    """How many DMs one backup round's slow loop asks about: what is left of the round's calls after
    `used` (the searches, and the DMs the "to:me" search already found)."""
    return max(1, CALLS_PER_MINUTE * poll_seconds // 60 - used - READ_RESERVE)


class Gate:
    """Every Slack call waits its turn here, like tickets at a deli counter: one call every
    60 / per_minute seconds, whichever job asks. Slack still says "too many calls"? Everyone
    waits as long as Slack asks (Retry-After), then the call is tried again.

    Use it like the WebClient it wraps: gate.conversations_info(channel=...).
    """

    def __init__(self, client, per_minute=CALLS_PER_MINUTE, clock=time.monotonic, sleep=time.sleep, on_ok=None):
        self.client = client
        self._gap = 60 / per_minute
        self._clock, self._sleep = clock, sleep
        self._on_ok = on_ok or (lambda: None)
        self._lock = threading.Lock()
        self._next = float("-inf")      # when the next call may go

    def __getattr__(self, name):        # runs for names Gate itself doesn't have: the WebClient's methods
        method = getattr(self.client, name)

        def call(**kwargs):
            for attempt in range(1, TRIES + 1):
                self._wait_turn()
                try:
                    answer = method(**kwargs)
                except SlackApiError as err:
                    if err.response.get("error") != "ratelimited" or attempt == TRIES:
                        raise
                    self._hold(retry_after(err))
                    continue
                self._on_ok()
                return answer
        return call

    def _wait_turn(self):
        with self._lock:                # take a ticket; the waiting happens outside the lock
            now = self._clock()
            mine = max(now, self._next)
            self._next = mine + self._gap
        if mine > now:
            self._sleep(mine - now)

    def _hold(self, seconds):
        with self._lock:
            self._next = max(self._next, self._clock() + seconds)


def retry_after(err):
    headers = getattr(err.response, "headers", None) or {}
    value = headers.get("Retry-After") or headers.get("retry-after") or "30"
    try:
        return float(value)
    except ValueError:
        return 30.0


class Live:
    """One running Slack connection. The ticker thread calls tick() every TICK_SECONDS; the
    doorbell calls on_request(); the page calls status(). Longer jobs (catch-up, backup rounds)
    run on their own thread so the read check keeps getting turns.

    env, web, socket, clock, now, sleep and background are swapped for fakes in tests.
    """

    def __init__(self, settings, inbox, env=os.environ, web=lambda token: WebClient(token=token),
                 socket=lambda app_token: SocketModeClient(app_token=app_token),
                 clock=time.monotonic, now=datetime.now, sleep=time.sleep, background=in_thread):
        self.settings, self.inbox = settings, inbox
        self.clock, self.now, self.sleep, self.background = clock, now, sleep, background
        self.socket_factory = socket
        user_token = env.get("SLACK_USER_TOKEN", "").strip()
        self.app_token = env.get("SLACK_APP_TOKEN", "").strip()
        seconds = settings["poll_seconds"]
        self.mode, self.reason = "instant", ""
        if settings["mode"] == "backup":
            self.mode, self.reason = "backup", (f"slack_mode=backup in settings.ini: checks Slack every {seconds} "
                                                f"seconds (new DMs can take a few minutes).")
        elif not self.app_token:
            self.mode, self.reason = "backup", (f"SLACK_APP_TOKEN is not set, so the app checks Slack every "
                                                f"{seconds} seconds instead of instantly (new DMs can take "
                                                f"a few minutes).")
        self.state = "running" if user_token else "off"     # off / running / error (stopped for good)
        self.problem = "" if user_token else NO_USER_TOKEN
        self.offline = False        # the last Slack call failed for network reasons
        self.client = Gate(web(user_token), clock=clock, sleep=sleep, on_ok=self._reached) if user_token else None
        self.look = None            # slack_inbox.Lookup, made once Slack says who you are
        self.socket = None
        self.socket_started = False
        self.need_catch_up = True   # on start, and after every lost connection
        self.busy = False           # a catch-up or backup round is running
        self.catching_up = False
        self.next_read = float("-inf")
        self.next_round = float("-inf")
        self.since = None           # backup rounds search from here
        self.dms, self.dm_next = [], 0

    # ----- the ticker -----

    def run(self):
        """The ticker thread: tick for as long as the app runs."""
        while self.state != "error":
            self.tick()
            self.sleep(TICK_SECONDS)

    def tick(self):
        if self.state != "running":
            return
        try:
            self._tick()
        except Exception as err:       # noqa: BLE001 - the ticker must never die silently
            self._failed(err)

    def _tick(self):
        if self.look is None:
            self.look = slack_inbox.Lookup(
                self.client, slack_inbox.who_am_i(self.client, groups=self.settings["count_groups"]))
        down = self.mode == "instant" and not self._doorbell_up()
        if down:
            self.need_catch_up = True       # whatever arrives now is missed: look for it once back
            if self.state != "running":
                return
        elif not self.busy:
            if self.need_catch_up:
                self.catching_up = True
                self._start(self._catch_up)
            elif self.mode == "backup" and self.clock() >= self.next_round:
                self._start(self._backup_round)
        if self.inbox.channels() and self.clock() >= self.next_read:
            calls = len(self.inbox.channels()) + len(self.inbox.threads())
            self.next_read = self.clock() + max(READ_CHECK_SECONDS, calls * READ_CALL_SECONDS)
            slack_inbox.read_check(self.look, self.inbox)

    def _doorbell_up(self):
        if self.socket is None:
            self.socket = self.socket_factory(self.app_token)
            self.socket.socket_mode_request_listeners.append(self.on_request)
        if not self.socket_started:     # once connected, slack_sdk reconnects on its own
            try:
                self.socket.connect()
            except SlackApiError as err:
                if err.response.get("error") == "ratelimited":
                    raise
                self._stop(BAD_APP_TOKEN)       # Slack refused the app token itself
                return False
            self.socket_started = True
        return self.socket.is_connected()

    # ----- longer jobs, on their own thread -----

    def _start(self, job):
        self.busy = True        # set before the thread starts, so the next tick can't start it twice

        def run():
            try:
                job()
            except Exception as err:   # noqa: BLE001
                self._failed(err)
            finally:
                self.busy = self.catching_up = False
        self.background(run)

    def _catch_up(self):
        self.need_catch_up = False
        started = self.now()
        try:
            slack_inbox.catch_up(self.look, self.settings, self.inbox, started)
        except Exception:
            self.need_catch_up = True       # try it all again on the next tick
            raise
        self.since = started - timedelta(seconds=SEARCH_MARGIN)
        self.next_round = self.clock() + self.settings["poll_seconds"]

    def _backup_round(self):
        """New mentions since the last round, DMs a "to:me" search finds, then the next batch of
        DMs in a slow loop (round and round), which catches anything the search missed."""
        started = self.now()
        try:
            slack_inbox.mention_check(self.look, self.settings, self.inbox, self.since)
            found = slack_inbox.recent_dms(self.client, self.since)
            for channel in found:
                slack_inbox.check_dm(self.look, self.settings, self.inbox, channel)
            self.since = started - timedelta(seconds=SEARCH_MARGIN)
            if self.dm_next >= len(self.dms):
                self.dms, self.dm_next = slack_inbox.dm_ids(self.client), 0
            used = len(slack_inbox.mention_queries(self.look, self.settings)) + 1 + len(found)
            for channel in self.dms[self.dm_next:self.dm_next + dm_batch(self.settings["poll_seconds"], used)]:
                slack_inbox.check_dm(self.look, self.settings, self.inbox, channel)
                self.dm_next += 1
        finally:        # failed or not, the next round waits its turn
            self.next_round = self.clock() + self.settings["poll_seconds"]

    # ----- the doorbell -----

    def on_request(self, socket, req):
        """Slack pushed something. Say "got it" first (Slack resends if we are slow), then handle it."""
        if req.type != "events_api":
            return
        socket.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        event = req.payload.get("event", {})
        if event.get("type") != "message" or self.state != "running" or self.look is None:
            return
        try:
            slack_inbox.on_message(event, self.look, self.settings, self.inbox)
        except Exception as err:       # noqa: BLE001
            self._failed(err)

    # ----- trouble -----

    def _reached(self):
        """A Slack call worked: whatever went wrong before is over (unless Slack is stopped for good)."""
        if self.state == "running":
            self.offline, self.problem = False, ""

    def _failed(self, err):
        if isinstance(err, SlackApiError):
            if err.response.get("error") in slack_inbox.LOGIN_ERRORS - {"ratelimited"}:
                self._stop(slack_inbox.plain_error(err))
            else:
                self.problem = slack_inbox.plain_error(err)     # e.g. too many calls: carry on
        elif isinstance(err, (OSError, http.client.HTTPException)):     # no network, VPN, timeout: try again
            self.offline, self.problem = True, slack_inbox.plain_error(err)
        else:
            self._stop(STOPPED.format(type(err).__name__))

    def _stop(self, message):
        self.state, self.problem = "error", message
        if self.socket:
            self.socket.close()

    # ----- for the page -----

    def status(self):
        """What the Slack button shows: state, a plain-English message, the mode, and the rows."""
        if self.state in ("off", "error"):
            state = self.state
        elif self.offline:
            state = "reconnecting"
        elif self.look is None:
            state = "checking"         # just started
        elif self.mode == "instant" and not (self.socket and self.socket.is_connected()):
            state = "reconnecting"
        elif self.catching_up:
            state = "checking"
        else:
            state = "connected"
        return {"state": state, "message": self.problem or self.reason, "mode": self.mode,
                **self.inbox.summary(self.now())}


_live = None
_start_lock = threading.Lock()


def start(settings, inbox, **fakes):
    """Start Slack once for the whole app (a second call gets the same one). No token = nothing runs."""
    global _live
    with _start_lock:
        if _live is None:
            _live = Live(settings, inbox, **fakes)
            if _live.state == "running":
                _live.background(_live.run)
        return _live
