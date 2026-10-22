"""Slack button rules: which messages glow, what a dropdown row shows, catch-up and read checks.

No Flask and no background threads here (slack_live.py runs those). Every Slack call goes through
`client`, a slack_sdk WebClient made with your user token (SLACK_USER_TOKEN, xoxp-); tests pass in
a fake one, so they never touch the network.
"""
import re
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from slack_sdk.errors import SlackApiError

PREVIEW_CHARS = 100     # one line in the dropdown
MAX_ROWS = 50           # per tab; the rest is "+N older"
SEARCH_PAGES = 5        # catch-up reads at most 500 matches per search (Slack allows ~20 searches a minute)
SLACK_ITSELF = {"USLACKBOT", "USLACK"}      # Slackbot and Slack's own tips: never glow
COUNTED_SUBTYPES = {None, "bot_message", "thread_broadcast", "file_share", "me_message"}     # not joins etc.
YES = {"yes", "true", "on", "1"}
NO = {"no", "false", "off", "0"}
# Codes Slack puts in message text: <@U123>, <!here>, <!subteam^S123|@team>, <#C123|name>, <https://…|label>
CODE = re.compile(r"<([^<>]*)>")
HERE = re.compile(r"<!(here|channel|everyone)(\|[^>]*)?>")
# A group mention: <!subteam^S123> in live messages, <@S123> in search results (group IDs start with S)
GROUP = re.compile(r"<(?:!subteam\^|@)(S\w+)(\|[^>]*)?>")
# Errors that mean the login itself is wrong: never hide these.
LOGIN_ERRORS = {"not_authed", "invalid_auth", "missing_scope", "token_revoked", "token_expired",
                "account_inactive", "ratelimited"}


def slack_settings(settings):
    """The slack_ lines of settings.ini (a dict from app.load_settings), checked, with defaults.

    A bad value stops the app with a plain-English message, like text_limit= does.
    """
    def number(key, default, smallest):
        value = settings.get(key, "").strip()
        if not value:
            return default
        if value.isdecimal() and int(value) >= smallest:
            return int(value)
        raise SystemExit(f'{key}= in settings.ini must be a whole number, {smallest} or more. It is "{value}".')

    def yes_no(key):
        value = settings.get(key, "").strip().lower()
        if not value or value in YES:
            return True
        if value in NO:
            return False
        raise SystemExit(f'{key}= in settings.ini must be yes or no. It is "{value}".')

    mode = settings.get("slack_mode", "").strip().lower() or "instant"
    if mode not in ("instant", "backup"):
        raise SystemExit(f'slack_mode= in settings.ini must be instant or backup. It is "{mode}".')
    return {"mode": mode,
            "poll_seconds": number("slack_poll_seconds", 30, 5),
            "lookback_days": number("slack_lookback_days", 7, 1),
            "count_bots": yes_no("slack_count_bots"),
            "count_here": yes_no("slack_count_here"),
            "count_groups": yes_no("slack_count_groups")}


def who_am_i(client, groups=True):
    """Your user ID, workspace ID, the user groups you are in, and every group's @handle.

    groups=False (slack_count_groups=no): groups aren't asked for, so usergroups:read isn't needed.
    """
    login = client.auth_test()
    me = {"user": login["user_id"], "team": login["team_id"], "groups": set(), "group_names": {}}
    if not groups:
        return me
    try:
        found = client.usergroups_list(include_users=True)["usergroups"]
    except SlackApiError as err:
        if err.response.get("error") in LOGIN_ERRORS:
            raise
        return me       # free Slack plans have no user groups
    for group in found:
        me["group_names"][group["id"]] = group["handle"]
        if me["user"] in group.get("users", []):
            me["groups"].add(group["id"])
    return me


def what_counts(message, channel_type, me, settings):
    """Does this new message make the button glow? Returns (kind, tags) or None.

    kind = "dm" (DM or group DM, any text) or "mention" (a channel message that names you).
    tags = why, shown on the row: "@you", "@here", "@rf-team", ..., plus "bot".
    """
    if message.get("subtype") not in COUNTED_SUBTYPES:
        return None
    if message.get("user") == me["user"] or message.get("user") in SLACK_ITSELF:
        return None
    bot = bool(message.get("bot_id")) or message.get("subtype") == "bot_message"
    if bot and not settings["count_bots"]:
        return None
    bot_tag = ["bot"] if bot else []
    if channel_type in ("im", "mpim"):
        return "dm", bot_tag
    text = message.get("text") or ""
    if f"<@{me['user']}>" in text or f"<@{me['user']}|" in text:
        return "mention", ["@you"] + bot_tag
    here = HERE.search(text)
    if here and settings["count_here"]:
        return "mention", ["@" + here.group(1)] + bot_tag
    if settings["count_groups"]:
        for group_id, _ in GROUP.findall(text):
            if group_id in me["groups"]:
                return "mention", ["@" + me["group_names"].get(group_id, "group")] + bot_tag
    return None


class Lookup:
    """Asks Slack for names of people and conversations, and remembers them (fewer Slack calls).

    client = the Slack WebClient; me = what who_am_i returned.
    """

    def __init__(self, client, me):
        self.client = client
        self.me = me
        self.people = {}        # user ID -> name
        self.infos = {}         # conversation ID -> what conversations.info said
        self.names = {}         # conversation ID -> "Mike" / "Mike, Dana"

    def person(self, user_id):
        if user_id not in self.people:
            try:
                user = self.client.users_info(user=user_id)["user"]
                profile = user.get("profile", {})
                self.people[user_id] = (profile.get("display_name") or profile.get("real_name")
                                        or user.get("real_name") or user.get("name") or user_id)
            except SlackApiError as err:
                if err.response.get("error") in LOGIN_ERRORS:
                    raise
                self.people[user_id] = user_id      # gone or hidden: show the ID, don't fail the row
        return self.people[user_id]

    def fresh_info(self, channel):
        """Ask Slack now (for last_read, which changes). Remembers the answer for names."""
        info = self.client.conversations_info(channel=channel)["channel"]
        self.infos[channel] = info
        return info

    def info(self, channel):
        return self.infos.get(channel) or self.fresh_info(channel)

    def where(self, channel):
        info = self.info(channel)
        if info.get("is_im"):
            return "DM"
        if info.get("is_mpim"):
            return "group DM"
        return "#" + info.get("name", channel)

    def conversation_name(self, channel):
        """Who a DM is with: "Mike", or "Mike, Dana" for a group DM (never you)."""
        if channel not in self.names:
            info = self.info(channel)
            if info.get("is_im"):
                self.names[channel] = self.person(info["user"])
            else:
                members = self.client.conversations_members(channel=channel)["members"]
                self.names[channel] = ", ".join(self.person(u) for u in members if u != self.me["user"])
        return self.names[channel]

    def sender(self, message):
        if message.get("user") and not message.get("bot_id"):
            return self.person(message["user"])
        return message.get("username") or message.get("bot_profile", {}).get("name") or "bot"


def preview(message, look):
    """The message as one short line: codes turned into names, links marked with 🔗."""
    def readable(match):
        code = match.group(1)
        target, _, label = code.partition("|")
        group = GROUP.fullmatch(match.group(0))
        if group:
            return "@" + (look.me["group_names"].get(group.group(1)) or label.lstrip("@") or "group")
        if target.startswith("@"):
            return "@" + look.person(target[1:])
        if target in ("!here", "!channel", "!everyone"):
            return "@" + target[1:]
        if target.startswith("!"):
            return label        # e.g. <!date^…|Oct 20>
        if target.startswith("#"):
            return "#" + (label or "channel")
        if label:
            return "🔗" + label
        if target.startswith("mailto:"):
            return "🔗" + target[len("mailto:"):]
        return "🔗" + (urlparse(target).hostname or target).removeprefix("www.")

    text = CODE.sub(readable, message.get("text") or "")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = " ".join(text.split())
    if not text and message.get("files"):
        text = "📎" + message["files"][0].get("name", "file")
    if len(text) > PREVIEW_CHARS:
        text = text[:PREVIEW_CHARS - 1] + "…"
    return text


def make_row(message, channel, kind, tags, look):
    """One unread message, ready for the Inbox. Asks Slack for names here, so summary() never has to."""
    ts = message["ts"]
    return {"kind": kind, "channel": channel, "ts": ts, "tags": tags,
            "thread": thread_of(message),        # the thread it replies in, or None
            "who": look.sender(message), "where": look.where(channel),
            "convo": look.conversation_name(channel) if kind == "dm" else "",
            "text": preview(message, look),
            "link": f"slack://channel?team={look.me['team']}&id={channel}&message={ts}"}


def thread_of(message):
    """The thread a message replies in (its first message's ts), or None. Search results have no
    thread_ts field: the thread is only in the permalink, as ?thread_ts=…
    """
    parent = (message.get("thread_ts")
              or parse_qs(urlparse(message.get("permalink", "")).query).get("thread_ts", [None])[0])
    return parent if parent and parent != message["ts"] else None


def thread_mark(client, channel, parent):
    """How far you have read inside one thread (Slack keeps it apart from the channel's), or None
    if Slack won't say. Login errors still stop everything.
    """
    try:
        first = client.conversations_replies(channel=channel, ts=parent, limit=1)["messages"][0]
    except SlackApiError as err:
        if err.response.get("error") in LOGIN_ERRORS:
            raise
        return None
    return first.get("last_read")


def stamp(ts):
    """Slack timestamps ("1729412345.123456") as exact numbers: a float would round the last digits."""
    return Decimal(ts or "0")


def when(ts, now):
    sent = datetime.fromtimestamp(float(ts))
    clock = f"{sent.hour}:{sent.minute:02}"
    return clock if sent.date() == now.date() else f"{sent:%b} {sent.day} {clock}"


class Inbox:
    """The unread rows behind the Slack button.

    Two parts of the app change it at the same time (new messages arriving, the read check
    removing rows), so every method holds the lock: one at a time, the other waits a moment.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._rows = {}         # (channel, ts) -> row from make_row

    def add(self, row):
        with self._lock:
            self._rows.setdefault((row["channel"], row["ts"]), row)     # already there = keep it

    def update_text(self, channel, ts, text):
        """An edited message: new preview, same row. An edit never adds a row."""
        with self._lock:
            if (channel, ts) in self._rows:
                self._rows[(channel, ts)]["text"] = text

    def has(self, channel, ts):
        with self._lock:
            return (channel, ts) in self._rows

    def remove(self, channel, ts):
        """A message deleted in Slack."""
        with self._lock:
            self._rows.pop((channel, ts), None)

    def opened(self, channel, ts):
        """You clicked a row. A DM row stands for the whole conversation, so all of it goes."""
        with self._lock:
            row = self._rows.pop((channel, ts), None)
            if row and row["kind"] == "dm":
                for key in [k for k, r in self._rows.items() if k[0] == channel and r["kind"] == "dm"]:
                    del self._rows[key]

    def drop_read(self, channel, last_read, thread=None):
        """Slack says you have read this conversation (or one thread in it) up to last_read: those rows go.

        Slack keeps a thread's read mark apart from the channel's, so the channel's mark never
        clears thread replies, and a thread's mark clears only that thread.
        """
        with self._lock:
            for key in [k for k, r in self._rows.items()
                        if k[0] == channel and r["thread"] == thread and stamp(k[1]) <= stamp(last_read)]:
                del self._rows[key]

    def forget_channel(self, channel):
        with self._lock:
            for key in [k for k in self._rows if k[0] == channel]:
                del self._rows[key]

    def channels(self):
        with self._lock:
            return {channel for channel, _ in self._rows}

    def threads(self):
        """(channel, thread) for every thread that has rows."""
        with self._lock:
            return {(channel, r["thread"]) for (channel, _), r in self._rows.items() if r["thread"]}

    def summary(self, now):
        """What the page shows: the full count, and up to MAX_ROWS rows per tab, newest first."""
        with self._lock:
            rows = sorted(self._rows.values(), key=lambda r: stamp(r["ts"]), reverse=True)
        mentions = [show(r, now) for r in rows if r["kind"] == "mention"]
        conversations = {}      # channel -> its rows, newest first
        for r in rows:
            if r["kind"] == "dm":
                conversations.setdefault(r["channel"], []).append(r)
        dms = []
        for convo in conversations.values():
            newest, first = convo[0], convo[-1]
            # Newest text, but the link (and the ts the page sends back) is the FIRST unread message.
            dms.append({**show(newest, now), "who": newest["convo"], "more": len(convo) - 1,
                        "ts": first["ts"], "link": first["link"]})
        return {"count": len(rows),
                "mentions": mentions[:MAX_ROWS], "mentions_more": max(0, len(mentions) - MAX_ROWS),
                "dms": dms[:MAX_ROWS], "dms_more": max(0, len(dms) - MAX_ROWS)}


def show(row, now):
    return {"who": row["who"], "where": row["where"], "when": when(row["ts"], now), "text": row["text"],
            "tags": row["tags"], "more": 0, "channel": row["channel"], "ts": row["ts"], "link": row["link"]}


def on_message(event, look, settings, inbox):
    """One message event pushed by Slack: new (maybe a row), edited (new preview) or deleted (row gone)."""
    channel = event.get("channel")
    subtype = event.get("subtype")
    if subtype == "message_deleted":
        inbox.remove(channel, event.get("deleted_ts"))
    elif subtype == "message_changed":
        message = event.get("message", {})
        if inbox.has(channel, message.get("ts")):        # no row = nothing to update, no Slack calls
            inbox.update_text(channel, message.get("ts"), preview(message, look))
    else:
        counted = what_counts(event, event.get("channel_type"), look.me, settings)
        if counted:
            inbox.add(make_row(event, channel, *counted, look))


def catch_up(look, settings, inbox, now):
    """Find what arrived while the app was off or disconnected: unread DMs of any age, and unread
    mentions from the last lookback_days. Rows go into the inbox as they are found.

    Slack has no "list my unread DMs" call, so every DM conversation is asked about, one by one.
    """
    for channel in dm_ids(look.client):
        check_dm(look, settings, inbox, channel)
    mention_check(look, settings, inbox, now - timedelta(days=settings["lookback_days"]))


def dm_ids(client):
    """Every DM and group DM you are in (not ones with deleted people)."""
    ids, cursor = [], None
    while True:
        page = client.users_conversations(types="im,mpim", exclude_archived=True, limit=200, cursor=cursor)
        ids += [convo["id"] for convo in page["channels"] if not convo.get("is_user_deleted")]
        cursor = page.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            return ids


def check_dm(look, settings, inbox, channel):
    """One DM conversation: its unread messages become rows. One Slack won't show is skipped."""
    try:
        info = look.fresh_info(channel)
        unread = info.get("unread_count_display", info.get("unread_count"))
        if unread == 0:         # missing = Slack didn't say: look anyway
            return
        history = look.client.conversations_history(channel=channel, oldest=info.get("last_read") or "0", limit=999)
    except SlackApiError as err:
        if err.response.get("error") in LOGIN_ERRORS:
            raise
        return          # closed or gone: don't let it block the other DMs
    kind = "mpim" if info.get("is_mpim") else "im"
    for message in history["messages"]:
        counted = what_counts(message, kind, look.me, settings)
        if counted:
            inbox.add(make_row(message, channel, *counted, look))


def mention_queries(look, settings):
    queries = [f"<@{look.me['user']}>"]
    if settings["count_here"]:
        queries += ["@here", "@channel", "@everyone"]
    if settings["count_groups"]:
        queries += [f"<@{group}>" for group in sorted(look.me["groups"])]     # <!subteam^…> matches everything
    return queries


def mention_check(look, settings, inbox, since):
    """Unread channel mentions of you (and @here, your groups...) sent after `since`."""
    asked = {}      # channel -> its info, asked once per check (last_read must be fresh)
    marks = {}      # (channel, thread) -> your read mark in that thread
    for query in mention_queries(look, settings):
        for match in search(look.client, query, since):
            where = match.get("channel", {})
            if where.get("is_im") or where.get("is_mpim") or stamp(match["ts"]) < Decimal(since.timestamp()):
                continue        # DMs are checked on their own
            if where["id"] not in asked:
                try:
                    asked[where["id"]] = look.fresh_info(where["id"])
                except SlackApiError as err:
                    if err.response.get("error") != "channel_not_found":
                        raise
                    asked[where["id"]] = {}     # you left it, or it was deleted
            info = asked[where["id"]]
            if not info.get("is_member") or info.get("is_archived"):
                continue        # Slack doesn't notify you there either
            read = info.get("last_read")
            parent = thread_of(match)
            if parent:
                if (where["id"], parent) not in marks:
                    marks[(where["id"], parent)] = thread_mark(look.client, where["id"], parent)
                read = marks[(where["id"], parent)] or read
            if stamp(match["ts"]) <= stamp(read):
                continue        # already read
            counted = what_counts(match, "channel", look.me, settings)
            if counted and counted[0] == "mention":
                inbox.add(make_row(match, where["id"], *counted, look))


def recent_dms(client, since):
    """DMs and group DMs with messages to you since that time, found by one search (backup mode)."""
    ids = []
    for match in search(client, "to:me", since):
        where = match.get("channel", {})
        if (where.get("is_im") or where.get("is_mpim")) and where["id"] not in ids:
            ids.append(where["id"])
    return ids


def search(client, query, since):
    """Every search match since that time, newest first, up to SEARCH_PAGES pages of 100."""
    page, pages = 1, 1
    while page <= min(pages, SEARCH_PAGES):
        # after: means "after that whole day", so one day earlier; catch_up cuts exactly
        result = client.search_messages(query=f"{query} after:{since.date() - timedelta(days=1)}",
                                        count=100, sort="timestamp", sort_dir="desc", page=page)
        matches = result["messages"]["matches"]
        yield from matches
        if matches and stamp(matches[-1]["ts"]) < Decimal(since.timestamp()):
            break       # newest first: the next pages are older still
        pages = result["messages"].get("paging", {}).get("pages", 1)
        page += 1


def read_check(look, inbox):
    """Ask Slack how far you have read in each conversation that has rows; drop what you read."""
    for channel in inbox.channels():
        try:
            info = look.fresh_info(channel)
        except SlackApiError as err:
            if err.response.get("error") != "channel_not_found":
                raise
            inbox.forget_channel(channel)       # you left it, or it was deleted
            continue
        if info.get("last_read"):
            inbox.drop_read(channel, info["last_read"])
    for channel, parent in inbox.threads():
        mark = thread_mark(look.client, channel, parent)
        if mark:
            inbox.drop_read(channel, mark, thread=parent)


def plain_error(err):
    """Any error from a Slack call, in plain English for the page."""
    if not isinstance(err, SlackApiError):
        return "Could not reach Slack. Check the internet / VPN."
    code = err.response.get("error", "")
    if code in ("not_authed", "invalid_auth"):
        return ("Slack login failed. Check SLACK_USER_TOKEN (the User OAuth Token, xoxp-…) "
                "in this Terminal, then restart the app.")
    if code == "missing_scope":
        needed = err.response.get("needed", "a permission")
        return (f"The Slack app is missing a permission ({needed}). Add it under OAuth & Permissions, "
                "reinstall the app, and set the new SLACK_USER_TOKEN.")
    if code in ("token_revoked", "token_expired"):
        return "Your Slack login was removed. Reinstall the Slack app and set SLACK_USER_TOKEN again."
    if code == "account_inactive":
        return "This Slack account is deactivated."
    if code == "ratelimited":
        return "Slack says too many calls. The app waits and tries again."
    return f'Slack answered with error "{code}".'
