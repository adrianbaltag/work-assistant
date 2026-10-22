"""Slack button rules: what glows, how rows look, catch-up and read checks. A fake Slack, so no network.

All IDs here are made up. Never put real workspace, user or channel IDs in this public repo.
"""
from datetime import datetime, timedelta

import pytest
from slack_sdk.errors import SlackApiError

import slack_inbox

NOW = datetime(2026, 10, 20, 9, 30)     # local time
ME, MIKE, DANA, TEAM = "U0ME", "U0MIKE", "U0DANA", "T0TEAM"
OPS, DM_MIKE, GDM = "C0OPS", "D0MIKE", "G0GDM"        # a channel, a DM, a group DM
SETTINGS = slack_inbox.slack_settings({})
MY_GROUP, OTHER_GROUP = "S0RF", "S0SALES"


def ts(minutes_ago=0, at=NOW):
    """A Slack message timestamp, minutes before NOW."""
    return f"{(at - timedelta(minutes=minutes_ago)).timestamp():.6f}"


def msg(text="hi", user=MIKE, minutes_ago=0, **extra):
    return {"type": "message", "user": user, "text": text, "ts": ts(minutes_ago), **extra}


def error(code, **extra):
    return SlackApiError(f"The request failed: {code}", {"ok": False, "error": code, **extra})


class FakeSlack:
    """Stands in for slack_sdk's WebClient: canned answers, and a list of every call made."""

    def __init__(self):
        self.calls = []
        self.fail = {}          # method name -> SlackApiError to raise
        self.people = {MIKE: "Mike", DANA: "Dana", ME: "Adrian"}
        self.channels = {
            OPS: {"id": OPS, "name": "ops", "is_channel": True, "is_member": True, "last_read": ts(60)},
            DM_MIKE: {"id": DM_MIKE, "is_im": True, "user": MIKE, "last_read": ts(60), "unread_count_display": 0},
            GDM: {"id": GDM, "is_mpim": True, "last_read": ts(60), "unread_count_display": 0},
        }
        self.members = {GDM: [ME, MIKE, DANA]}
        self.history = {}       # channel -> messages
        self.dm_pages = [[{"id": DM_MIKE, "is_im": True, "user": MIKE}, {"id": GDM, "is_mpim": True}]]
        self.matches = {}       # search query (without after:) -> matches
        self.threads = {}       # (channel, parent ts) -> your read mark in that thread
        self.groups = [{"id": MY_GROUP, "handle": "rf-team", "users": [ME, MIKE]},
                       {"id": OTHER_GROUP, "handle": "sales", "users": [DANA]}]

    def call(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name in self.fail:
            raise self.fail[name]

    def names(self):
        return [name for name, _ in self.calls]

    def auth_test(self):
        self.call("auth_test")
        return {"ok": True, "user_id": ME, "team_id": TEAM}

    def usergroups_list(self, **kwargs):
        self.call("usergroups_list", **kwargs)
        return {"ok": True, "usergroups": self.groups}

    def users_info(self, user):
        self.call("users_info", user=user)
        if user not in self.people:
            raise error("user_not_found")
        return {"ok": True, "user": {"id": user, "name": user.lower(), "profile": {"display_name": self.people[user]}}}

    def conversations_info(self, channel):
        self.call("conversations_info", channel=channel)
        if channel not in self.channels:
            raise error("channel_not_found")
        return {"ok": True, "channel": dict(self.channels[channel])}

    def conversations_members(self, channel, **kwargs):
        self.call("conversations_members", channel=channel)
        return {"ok": True, "members": self.members[channel]}

    def conversations_history(self, channel, oldest, **kwargs):
        self.call("conversations_history", channel=channel, oldest=oldest)
        newer = [m for m in self.history.get(channel, []) if float(m["ts"]) > float(oldest)]
        return {"ok": True, "messages": sorted(newer, key=lambda m: m["ts"], reverse=True)}

    def users_conversations(self, cursor=None, **kwargs):
        self.call("users_conversations", cursor=cursor, **kwargs)
        page = int(cursor or 0)
        more = str(page + 1) if page + 1 < len(self.dm_pages) else ""
        return {"ok": True, "channels": self.dm_pages[page], "response_metadata": {"next_cursor": more}}

    def conversations_replies(self, channel, ts, **kwargs):
        self.call("conversations_replies", channel=channel, ts=ts)
        if (channel, ts) not in self.threads:
            raise error("thread_not_found")
        return {"ok": True, "messages": [{"ts": ts, "last_read": self.threads[(channel, ts)], "subscribed": True}]}

    def search_messages(self, query, page=1, **kwargs):
        self.call("search_messages", query=query, page=page)
        pages = self.matches.get(query.split(" after:")[0], [])
        if not pages or isinstance(pages[0], dict):     # one page of matches, or a list of pages
            pages = [pages]
        return {"ok": True, "messages": {"matches": pages[page - 1], "paging": {"pages": len(pages), "page": page}}}


@pytest.fixture
def slack():
    return FakeSlack()


@pytest.fixture
def look(slack):
    return slack_inbox.Lookup(slack, slack_inbox.who_am_i(slack))


def found(m, channel=OPS, name="ops"):
    """A search result: the message plus the channel it is in."""
    return {**m, "channel": {"id": channel, "name": name}}


# ---------- slack_settings: the slack_ lines in settings.ini ----------

def test_settings_defaults():
    assert slack_inbox.slack_settings({}) == {"mode": "instant", "poll_seconds": 30, "lookback_days": 7,
                                              "count_bots": True, "count_here": True, "count_groups": True}


def test_settings_read_numbers_and_yes_no():
    got = slack_inbox.slack_settings({"slack_mode": " Backup ", "slack_poll_seconds": " 45 ", "slack_lookback_days": "3",
                                      "slack_count_bots": "No", "slack_count_here": "off", "slack_count_groups": ""})
    assert got == {"mode": "backup", "poll_seconds": 45, "lookback_days": 3, "count_bots": False,
                   "count_here": False, "count_groups": True}


@pytest.mark.parametrize("key, value", [("slack_poll_seconds", "thirty"), ("slack_poll_seconds", "2"),
                                        ("slack_lookback_days", "0"), ("slack_count_bots", "maybe"),
                                        ("slack_mode", "fast")])
def test_settings_bad_value_stops_with_plain_message(key, value):
    with pytest.raises(SystemExit, match=key):
        slack_inbox.slack_settings({key: value})


# ---------- who_am_i ----------

def test_who_am_i_finds_me_and_my_groups(slack):
    me = slack_inbox.who_am_i(slack)
    assert me["user"] == ME and me["team"] == TEAM
    assert me["groups"] == {MY_GROUP}
    assert me["group_names"] == {MY_GROUP: "rf-team", OTHER_GROUP: "sales"}


def test_who_am_i_without_user_groups(slack):
    slack.fail["usergroups_list"] = error("paid_teams_only")       # free Slack plans have no user groups
    assert slack_inbox.who_am_i(slack)["groups"] == set()


def test_who_am_i_bad_login_is_not_hidden(slack):
    slack.fail["usergroups_list"] = error("missing_scope", needed="usergroups:read")
    with pytest.raises(SlackApiError):
        slack_inbox.who_am_i(slack)


def test_who_am_i_with_groups_switched_off_never_asks_for_them(slack):
    slack.fail["usergroups_list"] = error("missing_scope", needed="usergroups:read")
    me = slack_inbox.who_am_i(slack, groups=False)      # slack_count_groups=no: that permission isn't needed
    assert me["user"] == ME and me["groups"] == set()
    assert "usergroups_list" not in slack.names()


# ---------- what_counts: does this message make the button glow? ----------

@pytest.fixture
def me(slack):
    return slack_inbox.who_am_i(slack)


def counts(message, channel_type="channel", settings=SETTINGS, me=None):
    me = me or {"user": ME, "team": TEAM, "groups": {MY_GROUP}, "group_names": {}}
    return slack_inbox.what_counts(message, channel_type, me, settings)


def test_any_dm_or_group_dm_counts():
    assert counts(msg("hello"), "im") == ("dm", [])
    assert counts(msg("hello"), "mpim") == ("dm", [])


def test_mention_inside_a_dm_counts_once_as_a_dm():
    assert counts(msg(f"<@{ME}> look"), "im") == ("dm", [])


def test_plain_channel_message_does_not_count():
    assert counts(msg("lunch?")) is None


def test_direct_mention_counts():
    assert counts(msg(f"<@{ME}> can you check site 1243?")) == ("mention", ["@you"])


@pytest.mark.parametrize("code, tag", [("<!here>", "@here"), ("<!channel>", "@channel"),
                                       ("<!everyone>", "@everyone"), ("<!here|here>", "@here")])
def test_here_channel_everyone_count(code, tag):
    assert counts(msg(f"{code} window moved")) == ("mention", [tag])


def test_here_can_be_switched_off():
    assert counts(msg("<!here> window moved"), settings={**SETTINGS, "count_here": False}) is None


def test_my_group_counts_other_groups_do_not():
    me = {"user": ME, "team": TEAM, "groups": {MY_GROUP}, "group_names": {MY_GROUP: "rf-team"}}
    assert counts(msg(f"<!subteam^{MY_GROUP}> please look"), me=me) == ("mention", ["@rf-team"])
    assert counts(msg(f"<!subteam^{OTHER_GROUP}> please look"), me=me) is None
    assert counts(msg(f"<!subteam^{MY_GROUP}> look"), settings={**SETTINGS, "count_groups": False}, me=me) is None


def test_group_mention_written_like_a_person_counts():
    # Search results write a group mention as <@S…>, not <!subteam^S…> (real Slack, 2026-10-20)
    me = {"user": ME, "team": TEAM, "groups": {MY_GROUP}, "group_names": {MY_GROUP: "rf-team"}}
    assert counts(msg(f"<@{MY_GROUP}> please look"), me=me) == ("mention", ["@rf-team"])
    assert counts(msg(f"<@{OTHER_GROUP}> please look"), me=me) is None


def test_my_own_messages_never_count():
    assert counts(msg("note to self", user=ME), "im") is None
    assert counts(msg(f"<@{ME}> reminder", user=ME)) is None


@pytest.mark.parametrize("user", ["USLACKBOT", "USLACK"])
def test_slacks_own_messages_never_count(user):
    assert counts(msg("Tips for Slack", user=user), "im") is None


def test_bots_count_with_a_tag_unless_switched_off():
    bot = msg("PROJ-1 assigned to you", user=None, bot_id="B0JIRA")
    assert counts(bot, "im") == ("dm", ["bot"])
    assert counts(msg(f"<@{ME}> build failed", subtype="bot_message", bot_id="B0CI")) == ("mention", ["@you", "bot"])
    assert counts(bot, "im", settings={**SETTINGS, "count_bots": False}) is None


def test_joins_and_other_system_messages_do_not_count():
    assert counts(msg(f"<@{MIKE}> has joined", subtype="channel_join"), "im") is None


def test_thread_reply_mention_counts():
    assert counts(msg(f"<@{ME}> in a thread", thread_ts=ts(5))) == ("mention", ["@you"])


# ---------- preview: one short line of text ----------

def test_preview_turns_codes_into_names(look):
    text = (f"<@{MIKE}> and <!subteam^{MY_GROUP}|@rf-team> <!here> see <#{OPS}|ops> "
            "&lt;now&gt; &amp; later")
    assert slack_inbox.preview(msg(text), look) == "@Mike and @rf-team @here see #ops <now> & later"


def test_preview_names_a_group_written_like_a_person(look):
    assert slack_inbox.preview(msg(f"<@{MY_GROUP}> and <@{OTHER_GROUP}> look"), look) == "@rf-team and @sales look"


def test_preview_marks_links(look):
    text = "see <https://example.sharepoint.com/x|Site plan> or <https://example.com/a/b> or <mailto:a@b.com|a@b.com>"
    assert slack_inbox.preview(msg(text), look) == "see 🔗Site plan or 🔗example.com or 🔗a@b.com"


def test_preview_is_one_short_line(look):
    assert slack_inbox.preview(msg("one\n\ntwo   three"), look) == "one two three"
    long = slack_inbox.preview(msg("x" * 300), look)
    assert len(long) == slack_inbox.PREVIEW_CHARS and long.endswith("…")


def test_preview_date_codes_show_their_label(look):
    assert slack_inbox.preview(msg("due <!date^1729412345^{date_short}|Oct 20> ok"), look) == "due Oct 20 ok"


def test_preview_of_a_file_without_text(look):
    assert slack_inbox.preview(msg("", files=[{"name": "site.xlsx"}]), look) == "📎site.xlsx"


# ---------- Lookup: names asked once ----------

def test_person_name_is_asked_once(look, slack):
    assert look.person(MIKE) == "Mike" and look.person(MIKE) == "Mike"
    assert slack.names().count("users_info") == 1


def test_unknown_person_shows_the_id(look):
    assert look.person("U0GONE") == "U0GONE"


def test_login_errors_in_a_name_lookup_are_not_hidden(look, slack):
    slack.fail["users_info"] = error("ratelimited")
    with pytest.raises(SlackApiError):
        look.person(MIKE)


def test_where_and_group_dm_names(look):
    assert look.where(OPS) == "#ops"
    assert look.where(DM_MIKE) == "DM"
    assert look.where(GDM) == "group DM"
    assert look.conversation_name(GDM) == "Mike, Dana"       # without me
    assert look.conversation_name(DM_MIKE) == "Mike"


# ---------- Inbox: the unread rows ----------

def row(look, m, channel=OPS, kind="mention", tags=("@you",)):
    return slack_inbox.make_row(m, channel, kind, list(tags), look)


def test_mention_row(look):
    inbox = slack_inbox.Inbox()
    m = msg(f"<@{ME}> check site 1243", minutes_ago=29)        # 9:01
    inbox.add(row(look, m))
    s = inbox.summary(NOW)
    assert s["count"] == 1 and s["dms"] == [] and s["mentions_more"] == 0
    assert s["mentions"] == [{"who": "Mike", "where": "#ops", "when": "9:01", "text": "@Adrian check site 1243",
                              "tags": ["@you"], "more": 0, "channel": OPS, "ts": m["ts"],
                              "link": f"slack://channel?team={TEAM}&id={OPS}&message={m['ts']}"}]


def test_when_shows_date_for_older_days(look):
    inbox = slack_inbox.Inbox()
    inbox.add(row(look, msg("old", minutes_ago=2 * 24 * 60 + 95)))      # Oct 18 7:55
    assert inbox.summary(NOW)["mentions"][0]["when"] == "Oct 18 7:55"


def test_same_message_twice_is_one_row(look):
    inbox = slack_inbox.Inbox()
    m = msg(f"<@{ME}> hi")
    inbox.add(row(look, m))
    inbox.add(row(look, m))
    assert inbox.summary(NOW)["count"] == 1


def test_dms_are_one_row_per_conversation(look):
    inbox = slack_inbox.Inbox()
    first, newest = msg("one", minutes_ago=5), msg("five", minutes_ago=1)
    for m in [first, msg("two", minutes_ago=4), msg("three", minutes_ago=3), msg("four", minutes_ago=2), newest]:
        inbox.add(row(look, m, DM_MIKE, "dm", []))
    s = inbox.summary(NOW)
    assert s["count"] == 5
    [dm] = s["dms"]
    assert (dm["who"], dm["where"], dm["text"], dm["more"]) == ("Mike", "DM", "five", 4)
    assert dm["ts"] == first["ts"] and dm["link"].endswith(f"message={first['ts']}")     # opens at the FIRST unread


def test_group_dm_row_names_everyone_but_me(look):
    inbox = slack_inbox.Inbox()
    inbox.add(row(look, msg("hi all", user=DANA), GDM, "dm", []))
    assert inbox.summary(NOW)["dms"][0]["who"] == "Mike, Dana"


def test_newest_first_and_at_most_50_rows(look):
    inbox = slack_inbox.Inbox()
    for i in range(60):
        inbox.add(row(look, msg(f"m{i}", minutes_ago=i)))
    s = inbox.summary(NOW)
    assert s["count"] == 60 and len(s["mentions"]) == 50 and s["mentions_more"] == 10
    assert s["mentions"][0]["text"] == "m0"


def test_opened_mention_removes_only_that_row(look):
    inbox = slack_inbox.Inbox()
    a, b = msg(f"<@{ME}> a", minutes_ago=2), msg(f"<@{ME}> b", minutes_ago=1)
    inbox.add(row(look, a))
    inbox.add(row(look, b))
    inbox.opened(OPS, a["ts"])
    assert [r["ts"] for r in inbox.summary(NOW)["mentions"]] == [b["ts"]]


def test_opened_dm_row_clears_the_whole_conversation(look):
    inbox = slack_inbox.Inbox()
    a, b = msg("a", minutes_ago=2), msg("b", minutes_ago=1)
    inbox.add(row(look, a, DM_MIKE, "dm", []))
    inbox.add(row(look, b, DM_MIKE, "dm", []))
    inbox.opened(DM_MIKE, a["ts"])
    assert inbox.summary(NOW)["count"] == 0


def test_drop_read_removes_rows_up_to_last_read_in_that_channel_only(look):
    inbox = slack_inbox.Inbox()
    old, new = msg(f"<@{ME}> old", minutes_ago=10), msg(f"<@{ME}> new", minutes_ago=1)
    inbox.add(row(look, old))
    inbox.add(row(look, new))
    inbox.add(row(look, msg("dm", minutes_ago=10), DM_MIKE, "dm", []))
    assert inbox.channels() == {OPS, DM_MIKE}
    inbox.drop_read(OPS, old["ts"])
    s = inbox.summary(NOW)
    assert [r["ts"] for r in s["mentions"]] == [new["ts"]] and s["count"] == 2


# ---------- on_message: one pushed Slack event ----------

def test_new_message_event_adds_a_row(look):
    inbox = slack_inbox.Inbox()
    slack_inbox.on_message({**msg("hi"), "channel": DM_MIKE, "channel_type": "im"}, look, SETTINGS, inbox)
    slack_inbox.on_message({**msg("lunch?"), "channel": OPS, "channel_type": "channel"}, look, SETTINGS, inbox)
    assert inbox.summary(NOW)["count"] == 1


def test_edit_updates_the_preview_but_never_adds(look):
    inbox = slack_inbox.Inbox()
    m = msg("site 1234")
    inbox.add(row(look, m, DM_MIKE, "dm", []))
    edit = {"type": "message", "subtype": "message_changed", "channel": DM_MIKE, "channel_type": "im",
            "message": {**m, "text": "site 1243"}}
    slack_inbox.on_message(edit, look, SETTINGS, inbox)
    added = {"type": "message", "subtype": "message_changed", "channel": OPS, "channel_type": "channel",
             "message": msg(f"<@{ME}> added later", minutes_ago=3)}
    slack_inbox.on_message(added, look, SETTINGS, inbox)
    s = inbox.summary(NOW)
    assert s["dms"][0]["text"] == "site 1243" and s["count"] == 1


def test_edit_without_a_row_asks_slack_nothing(look, slack):
    slack.calls.clear()
    edit = {"type": "message", "subtype": "message_changed", "channel": OPS, "channel_type": "channel",
            "message": msg(f"<@{MIKE}> <@{DANA}> fixed typo")}
    slack_inbox.on_message(edit, look, SETTINGS, slack_inbox.Inbox())
    assert slack.calls == []


def test_delete_removes_the_row(look):
    inbox = slack_inbox.Inbox()
    m = msg("oops")
    inbox.add(row(look, m, DM_MIKE, "dm", []))
    slack_inbox.on_message({"type": "message", "subtype": "message_deleted", "channel": DM_MIKE,
                            "channel_type": "im", "deleted_ts": m["ts"]}, look, SETTINGS, inbox)
    assert inbox.summary(NOW)["count"] == 0


# ---------- catch_up: what arrived while the app was off ----------

def test_catch_up_finds_unread_dms_of_any_age(look, slack):
    slack.dm_pages = [[{"id": "D0OLD", "is_im": True, "user": DANA}], [{"id": DM_MIKE, "is_im": True, "user": MIKE}]]
    slack.channels["D0OLD"] = {"id": "D0OLD", "is_im": True, "user": DANA, "last_read": ts(60 * 24 * 400),
                               "unread_count_display": 1}
    slack.history["D0OLD"] = [msg("from last year", user=DANA, minutes_ago=60 * 24 * 300)]
    slack.channels[DM_MIKE]["unread_count_display"] = 2
    slack.history[DM_MIKE] = [msg("read already", minutes_ago=90), msg("new 1", minutes_ago=5),
                              msg("my reply", user=ME, minutes_ago=4), msg("new 2", minutes_ago=3)]
    inbox = slack_inbox.Inbox()
    slack_inbox.catch_up(look, SETTINGS, inbox, NOW)
    s = inbox.summary(NOW)
    assert s["count"] == 3
    assert {r["who"]: r["more"] for r in s["dms"]} == {"Mike": 1, "Dana": 0}
    assert ("conversations_history", {"channel": DM_MIKE, "oldest": slack.channels[DM_MIKE]["last_read"]}) in slack.calls


def test_catch_up_skips_read_dms_and_deleted_users(look, slack):
    slack.dm_pages = [[{"id": DM_MIKE, "is_im": True, "user": MIKE},
                       {"id": "D0GONE", "is_im": True, "user": "U0GONE", "is_user_deleted": True}]]
    slack_inbox.catch_up(look, SETTINGS, slack_inbox.Inbox(), NOW)
    assert "conversations_history" not in slack.names()          # Mike's DM: 0 unread
    assert ("conversations_info", {"channel": "D0GONE"}) not in slack.calls


def test_catch_up_finds_unread_mentions_in_the_lookback(look, slack):
    slack.dm_pages = [[]]
    unread, read = msg(f"<@{ME}> new", minutes_ago=5), msg(f"<@{ME}> seen", minutes_ago=90)
    too_old = msg(f"<@{ME}> ancient", minutes_ago=60 * 24 * 8)
    slack.channels[OPS]["last_read"] = ts(60 * 24 * 30)
    slack.channels["C0SEEN"] = {"id": "C0SEEN", "name": "seen", "is_member": True, "last_read": ts(60)}
    slack.channels["C0OUT"] = {"id": "C0OUT", "name": "out", "is_member": False}
    slack.channels["C0OLD"] = {"id": "C0OLD", "name": "old", "is_member": True, "is_archived": True,
                               "last_read": "0000000000.000000"}
    slack.matches[f"<@{ME}>"] = [found(unread), found(read, "C0SEEN", "seen"), found(too_old),
                                 found(msg(f"<@{ME}> not in it"), "C0OUT", "out"),
                                 found(msg(f"<@{ME}> archived"), "C0OLD", "old"),
                                 {**msg(f"<@{ME}> in a DM"), "channel": {"id": DM_MIKE, "is_im": True}}]
    inbox = slack_inbox.Inbox()
    slack_inbox.catch_up(look, SETTINGS, inbox, NOW)
    assert [r["text"] for r in inbox.summary(NOW)["mentions"]] == ["@Adrian new"]


def test_catch_up_searches_here_and_my_groups_since_the_lookback(look, slack):
    slack.dm_pages = [[]]
    slack.matches["@here"] = [found(msg("<!here> moved", minutes_ago=5))]
    slack.matches[f"<@{MY_GROUP}>"] = [found(msg(f"<@{MY_GROUP}> look", minutes_ago=6))]
    slack.channels[OPS]["last_read"] = ts(60)
    inbox = slack_inbox.Inbox()
    slack_inbox.catch_up(look, SETTINGS, inbox, NOW)
    assert inbox.summary(NOW)["count"] == 2
    queries = [kw["query"] for name, kw in slack.calls if name == "search_messages"]
    assert f"<@{ME}> after:2026-10-12" in queries and len(queries) == 5      # me, here, channel, everyone, rf-team
    assert f"<@{MY_GROUP}> after:2026-10-12" in queries     # <!subteam^…> would match every message
    slack.calls.clear()
    slack_inbox.catch_up(look, {**SETTINGS, "count_here": False, "count_groups": False}, inbox, NOW)
    assert [kw["query"] for name, kw in slack.calls if name == "search_messages"] == [f"<@{ME}> after:2026-10-12"]


def test_catch_up_reads_every_search_page(look, slack):
    slack.dm_pages = [[]]
    slack.channels[OPS]["last_read"] = ts(60)
    slack.matches[f"<@{ME}>"] = [[found(msg(f"<@{ME}> page 1", minutes_ago=5))],
                                 [found(msg(f"<@{ME}> page 2", minutes_ago=6))]]
    inbox = slack_inbox.Inbox()
    slack_inbox.catch_up(look, SETTINGS, inbox, NOW)
    assert inbox.summary(NOW)["count"] == 2


def test_dm_ids_lists_every_page_and_skips_deleted_users(slack):
    slack.dm_pages = [[{"id": DM_MIKE, "is_im": True, "user": MIKE},
                       {"id": "D0GONE", "is_im": True, "user": "U0GONE", "is_user_deleted": True}],
                      [{"id": GDM, "is_mpim": True}]]
    assert slack_inbox.dm_ids(slack) == [DM_MIKE, GDM]


def test_check_dm_adds_the_unread_messages_of_one_conversation(look, slack):
    slack.channels[DM_MIKE]["unread_count_display"] = 1
    slack.history[DM_MIKE] = [msg("new", minutes_ago=5)]
    inbox = slack_inbox.Inbox()
    slack_inbox.check_dm(look, SETTINGS, inbox, DM_MIKE)
    assert [r["text"] for r in inbox.summary(NOW)["dms"]] == ["new"]
    assert slack.names() == ["auth_test", "usergroups_list", "conversations_info", "conversations_history",
                             "users_info"]


def test_check_dm_skips_a_conversation_slack_will_not_show(look, slack):
    slack.fail["conversations_info"] = error("channel_not_found")
    inbox = slack_inbox.Inbox()
    slack_inbox.check_dm(look, SETTINGS, inbox, DM_MIKE)       # no error: the others still get checked
    assert inbox.summary(NOW)["count"] == 0


def test_check_dm_still_stops_on_login_errors(look, slack):
    slack.fail["conversations_info"] = error("invalid_auth")
    with pytest.raises(SlackApiError):
        slack_inbox.check_dm(look, SETTINGS, slack_inbox.Inbox(), DM_MIKE)


def test_search_stops_paging_once_results_are_older_than_wanted(slack):
    slack.matches["@here"] = [[found(msg("<!here> new", minutes_ago=1)), found(msg("<!here> old", minutes_ago=30))],
                              [found(msg("<!here> older", minutes_ago=60))]]
    got = list(slack_inbox.search(slack, "@here", NOW - timedelta(minutes=10)))
    assert len(got) == 2 and slack.names() == ["search_messages"]


def test_mention_check_only_keeps_mentions_since_the_time_given(look, slack):
    slack.channels[OPS]["last_read"] = ts(60 * 24)
    slack.matches[f"<@{ME}>"] = [found(msg(f"<@{ME}> new", minutes_ago=1)), found(msg(f"<@{ME}> older", minutes_ago=10))]
    inbox = slack_inbox.Inbox()
    slack_inbox.mention_check(look, SETTINGS, inbox, NOW - timedelta(minutes=5))
    assert [r["text"] for r in inbox.summary(NOW)["mentions"]] == ["@Adrian new"]
    assert "users_conversations" not in slack.names()       # no DM work


def test_mention_check_skips_a_channel_slack_will_not_show(look, slack):
    slack.channels[OPS]["last_read"] = ts(60)
    slack.matches[f"<@{ME}>"] = [found(msg(f"<@{ME}> gone", minutes_ago=1), "C0GONE", "gone"),
                                 found(msg(f"<@{ME}> here", minutes_ago=2))]
    inbox = slack_inbox.Inbox()
    slack_inbox.mention_check(look, SETTINGS, inbox, NOW - timedelta(minutes=5))   # no error
    assert [r["text"] for r in inbox.summary(NOW)["mentions"]] == ["@Adrian here"]


def test_mention_check_still_stops_on_login_errors(look, slack):
    slack.matches[f"<@{ME}>"] = [found(msg(f"<@{ME}> hi", minutes_ago=1))]
    slack.fail["conversations_info"] = error("invalid_auth")
    with pytest.raises(SlackApiError):
        slack_inbox.mention_check(look, SETTINGS, slack_inbox.Inbox(), NOW - timedelta(minutes=5))


# ---------- read_check: did you read it in the Slack app? ----------

def test_read_check_asks_only_about_channels_with_rows(look, slack):
    inbox = slack_inbox.Inbox()
    inbox.add(row(look, msg(f"<@{ME}> a", minutes_ago=30)))
    inbox.add(row(look, msg("dm", minutes_ago=30), DM_MIKE, "dm", []))
    slack.channels[OPS]["last_read"] = ts(10)                   # read in Slack since
    slack.calls.clear()
    slack_inbox.read_check(look, inbox)
    assert sorted(kw["channel"] for name, kw in slack.calls) == sorted([DM_MIKE, OPS])
    assert inbox.summary(NOW)["mentions"] == [] and len(inbox.summary(NOW)["dms"]) == 1


def test_read_check_uses_the_threads_own_read_mark(look, slack):
    # Slack keeps a thread's read mark apart from the channel's: reading newer channel messages
    # must not clear an unread thread mention, but reading the thread must.
    inbox = slack_inbox.Inbox()
    inbox.add(row(look, msg(f"<@{ME}> in a thread", minutes_ago=5, thread_ts=ts(20))))
    slack.channels[OPS]["last_read"] = ts(1)
    slack.threads[(OPS, ts(20))] = ts(10)                       # thread not read since
    slack_inbox.read_check(look, inbox)
    assert inbox.summary(NOW)["count"] == 1
    slack.threads[(OPS, ts(20))] = ts(5)                        # now read in Slack
    slack_inbox.read_check(look, inbox)
    assert inbox.summary(NOW)["count"] == 0


def test_read_check_asks_about_each_thread_once(look, slack):
    inbox = slack_inbox.Inbox()
    for minutes in (5, 6):
        inbox.add(row(look, msg(f"<@{ME}> reply {minutes}", minutes_ago=minutes, thread_ts=ts(20))))
    slack.threads[(OPS, ts(20))] = ts(30)
    slack.calls.clear()
    slack_inbox.read_check(look, inbox)
    assert slack.names().count("conversations_replies") == 1


def test_read_check_keeps_a_thread_row_slack_will_not_show(look, slack):
    inbox = slack_inbox.Inbox()
    inbox.add(row(look, msg(f"<@{ME}> in a thread", minutes_ago=5, thread_ts=ts(20))))
    slack_inbox.read_check(look, inbox)                         # thread_not_found: no error, row stays
    assert inbox.summary(NOW)["count"] == 1
    slack.fail["conversations_replies"] = error("invalid_auth")
    with pytest.raises(SlackApiError):
        slack_inbox.read_check(look, inbox)


def in_thread(m, parent):
    """A thread reply as search returns it: no thread_ts field, the thread only in the permalink."""
    return {**found(m), "permalink": f"https://example.slack.com/archives/{OPS}/p{m['ts'].replace('.', '')}"
                                     f"?thread_ts={parent}&cid={OPS}"}


def test_catch_up_judges_a_thread_mention_by_the_threads_read_mark(look, slack):
    slack.dm_pages = [[]]
    read, unread = msg(f"<@{ME}> read reply", minutes_ago=5), msg(f"<@{ME}> unread reply", minutes_ago=6)
    slack.matches[f"<@{ME}>"] = [in_thread(read, ts(30)), in_thread(unread, ts(40))]
    slack.channels[OPS]["last_read"] = ts(1)        # channel read after both replies
    slack.threads[(OPS, ts(30))] = ts(5)
    slack.threads[(OPS, ts(40))] = ts(41)
    inbox = slack_inbox.Inbox()
    slack_inbox.catch_up(look, SETTINGS, inbox, NOW)
    assert [r["text"] for r in inbox.summary(NOW)["mentions"]] == ["@Adrian unread reply"]
    slack_inbox.read_check(look, inbox)             # it is a thread row: the channel mark doesn't clear it
    assert inbox.summary(NOW)["count"] == 1


def test_catch_up_thread_without_a_read_mark_uses_the_channels(look, slack):
    slack.dm_pages = [[]]
    slack.matches[f"<@{ME}>"] = [in_thread(msg(f"<@{ME}> reply", minutes_ago=5), ts(30))]
    slack.channels[OPS]["last_read"] = ts(1)
    slack.threads[(OPS, ts(30))] = None
    inbox = slack_inbox.Inbox()
    slack_inbox.catch_up(look, SETTINGS, inbox, NOW)
    assert inbox.summary(NOW)["count"] == 0


def test_the_first_message_of_a_thread_is_not_a_reply(look, slack):
    slack.dm_pages = [[]]
    parent = msg(f"<@{ME}> start", minutes_ago=5)
    slack.matches[f"<@{ME}>"] = [in_thread(parent, parent["ts"])]
    slack.channels[OPS]["last_read"] = ts(60)
    inbox = slack_inbox.Inbox()
    slack_inbox.catch_up(look, SETTINGS, inbox, NOW)
    assert inbox.summary(NOW)["count"] == 1 and "conversations_replies" not in slack.names()


# ---------- recent_dms: backup mode's quick look for new DMs ----------

def test_recent_dms_lists_each_dm_found_by_search_once(slack):
    slack.matches["to:me"] = [{**msg("a"), "channel": {"id": DM_MIKE, "is_im": True}},
                              {**msg("b"), "channel": {"id": DM_MIKE, "is_im": True}},
                              {**msg("c"), "channel": {"id": GDM, "is_mpim": True}},
                              found(msg("not a DM"))]
    assert slack_inbox.recent_dms(slack, NOW - timedelta(minutes=10)) == [DM_MIKE, GDM]


def test_read_check_forgets_a_channel_that_is_gone(look, slack):
    inbox = slack_inbox.Inbox()
    inbox.add(row(look, msg(f"<@{ME}> a")))
    del slack.channels[OPS]                                     # left the channel, or it was deleted
    slack_inbox.read_check(look, inbox)
    assert inbox.summary(NOW)["count"] == 0


# ---------- plain_error: Slack's error codes in plain English ----------

@pytest.mark.parametrize("code, words", [("not_authed", "SLACK_USER_TOKEN"), ("invalid_auth", "SLACK_USER_TOKEN"),
                                         ("token_revoked", "Reinstall"), ("account_inactive", "deactivated"),
                                         ("ratelimited", "too many"), ("weird_thing", "weird_thing")])
def test_plain_error(code, words):
    assert words in slack_inbox.plain_error(error(code))


def test_plain_error_missing_scope_names_the_permission():
    assert "usergroups:read" in slack_inbox.plain_error(error("missing_scope", needed="usergroups:read"))


def test_plain_error_when_slack_cannot_be_reached():
    assert "internet" in slack_inbox.plain_error(OSError("Name or service not known"))
