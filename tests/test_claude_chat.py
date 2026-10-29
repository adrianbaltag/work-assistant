"""Ask Claude: what the app sends to Claude, and how it reads the answer. A fake client, so no tokens are spent."""
import os
import time
from datetime import datetime
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

import claude_chat

NOW = datetime(2026, 10, 16, 9, 30)
NOTE = "---\ntitle: Northeast report\nstatus: active\nnext: ask vendor\n---\n## Goal\nBuild it\n"


def make_project(tmp_path, files=None):
    """A project folder with note.md plus {"raw/x.txt": "text" or bytes}. Later entries = newer files."""
    folder = tmp_path / "DEMO-1"
    folder.mkdir()
    (folder / "note.md").write_text(NOTE, encoding="utf-8")
    for i, (name, data) in enumerate((files or {}).items()):
        path = folder / name
        path.parent.mkdir(exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")
        stamp = time.time() - 1000 + i         # each file a second newer than the one before
        os.utime(path, (stamp, stamp))
    return folder


def texts(blocks):
    return [b["text"] for b in blocks if b["type"] == "text"]


# ---------- project_context: what Claude gets to read ----------

def test_context_starts_with_today_and_the_note(tmp_path):
    blocks, skipped = claude_chat.project_context(make_project(tmp_path), NOW)
    assert "2026-10-16" in texts(blocks)[0]
    assert "next: ask vendor" in texts(blocks)[0]
    assert skipped == []


def test_context_has_session_and_raw_text_files_with_their_names(tmp_path):
    folder = make_project(tmp_path, {"sessions/2026-10-14.md": "met the team", "raw/reply.txt": "Only Northeast"})
    all_text = "\n".join(texts(claude_chat.project_context(folder, NOW)[0]))
    assert "sessions/2026-10-14.md" in all_text and "met the team" in all_text
    assert "raw/reply.txt" in all_text and "Only Northeast" in all_text


def test_context_puts_newest_files_first(tmp_path):
    folder = make_project(tmp_path, {"raw/old.txt": "OLD", "raw/new.txt": "NEW"})
    all_text = "\n".join(texts(claude_chat.project_context(folder, NOW)[0]))
    assert all_text.index("NEW") < all_text.index("OLD")


def test_context_skips_older_text_over_the_size_cap(tmp_path):
    folder = make_project(tmp_path, {"raw/old.txt": "o" * 600, "raw/new.txt": "n" * 600})
    blocks, skipped = claude_chat.project_context(folder, NOW, cap=1000)
    assert "n" * 600 in "\n".join(texts(blocks))
    assert "o" * 600 not in "\n".join(texts(blocks))
    assert skipped == ["raw/old.txt (over the 1,000-character limit: raise text_limit= in settings.ini)"]


def test_context_cap_defaults_to_200_000_characters(tmp_path):
    folder = make_project(tmp_path, {"raw/big.txt": "b" * 150_000, "raw/bigger.txt": "c" * 60_000})
    _, skipped = claude_chat.project_context(folder, NOW)
    assert skipped == ["raw/big.txt (over the 200,000-character limit: raise text_limit= in settings.ini)"]


def test_context_sends_images_as_base64_with_the_right_type(tmp_path):
    folder = make_project(tmp_path, {"raw/shot.png": b"\x89PNG fake", "raw/photo.JPG": b"jpeg"})
    images = [b for b in claude_chat.project_context(folder, NOW)[0] if b["type"] == "image"]
    assert {i["source"]["media_type"] for i in images} == {"image/png", "image/jpeg"}
    assert images[0]["source"]["type"] == "base64"


def test_context_skips_big_unsupported_and_too_many_images(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_chat, "IMAGE_BYTES", 10)
    monkeypatch.setattr(claude_chat, "IMAGE_COUNT", 1)
    folder = make_project(tmp_path, {"raw/older.png": b"png", "raw/huge.png": b"x" * 11,
                                     "raw/old.bmp": b"bmp", "raw/newest.png": b"png"})
    blocks, skipped = claude_chat.project_context(folder, NOW)
    assert len([b for b in blocks if b["type"] == "image"]) == 1
    assert "raw/huge.png (image over 5 MB)" in skipped
    assert "raw/old.bmp (image type Claude can't read)" in skipped
    assert "raw/older.png (more than 20 images; only the newest are sent)" in skipped


def test_context_lists_files_it_cannot_read(tmp_path):
    folder = make_project(tmp_path, {"raw/budget.xlsx": b"PK\x00\x01binary"})
    blocks, skipped = claude_chat.project_context(folder, NOW)
    assert skipped == ["raw/budget.xlsx (not a text file)"]
    assert "raw/budget.xlsx" in "\n".join(texts(blocks))      # Claude knows it exists


def test_context_marks_its_last_block_for_caching(tmp_path):
    blocks, _ = claude_chat.project_context(make_project(tmp_path, {"raw/a.txt": "a"}), NOW)
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in b for b in blocks[:-1])


# ---------- all_projects_context: the global Ask Claude page reads every open note.md ----------

def make_note(root, folder, note, days_ago=0):
    """root/folder/note.md with this text, last changed `days_ago` days ago."""
    path = root / folder
    path.mkdir(parents=True)
    (path / "note.md").write_text(note, encoding="utf-8")
    stamp = NOW.timestamp() - days_ago * 86400      # from NOW, not the real clock: the test runs on any day
    os.utime(path / "note.md", (stamp, stamp))
    return path


def test_all_context_has_every_open_note_and_how_old_it_is(tmp_path):
    make_note(tmp_path, "DEMO-1", "---\ntitle: Report\n---\nvendor late\n", days_ago=3)
    make_note(tmp_path, "DEMO-2", "---\ntitle: Parser\n---\nlogs in\n")
    blocks, skipped = claude_chat.all_projects_context(tmp_path, NOW)
    all_text = "\n".join(texts(blocks))
    assert "2026-10-16" in texts(blocks)[0]
    assert "=== DEMO-1/note.md (title: Report, status: active, priority: normal, updated 3 days ago) ===" in all_text
    assert "vendor late" in all_text
    assert "=== DEMO-2/note.md (title: Parser, status: active, priority: normal, updated today) ===" in all_text
    assert "logs in" in all_text
    assert skipped == []


def test_all_context_fills_in_missing_fields_like_the_dashboard(tmp_path):
    make_note(tmp_path, "DEMO-1", "just text, no fields\n")
    all_text = "\n".join(texts(claude_chat.all_projects_context(tmp_path, NOW)[0]))
    assert "(title: DEMO-1, status: active, priority: normal, updated today)" in all_text


def test_all_context_never_says_minus_days(tmp_path):
    make_note(tmp_path, "DEMO-1", "---\ntitle: Report\n---\n", days_ago=-2)      # clock ahead on a network drive
    all_text = "\n".join(texts(claude_chat.all_projects_context(tmp_path, NOW)[0]))
    assert "updated today" in all_text and "-" not in all_text.split("updated")[1].split(")")[0]


def test_all_context_skips_a_project_moved_while_reading(tmp_path, monkeypatch):
    make_note(tmp_path, "DEMO-1", "---\ntitle: Report\n---\n")
    listed = claude_chat.notes.list_projects(tmp_path)
    (tmp_path / "DEMO-1" / "note.md").unlink()          # archived in another tab, after the list was made
    monkeypatch.setattr(claude_chat.notes, "list_projects", lambda folder: listed)
    _, skipped = claude_chat.all_projects_context(tmp_path, NOW)
    assert skipped == ["DEMO-1/note.md (moved or deleted while reading)"]


def test_all_context_skips_archived_projects_and_project_files(tmp_path):
    folder = make_note(tmp_path, "DEMO-1", "---\ntitle: Open\n---\n")
    (folder / "raw").mkdir()
    (folder / "raw" / "mail.txt").write_text("SECRET RAW", encoding="utf-8")
    make_note(tmp_path, "_archive/OLD-1", "---\ntitle: Done long ago\n---\n")
    all_text = "\n".join(texts(claude_chat.all_projects_context(tmp_path, NOW)[0]))
    assert "Open" in all_text
    assert "Done long ago" not in all_text and "SECRET RAW" not in all_text


def test_all_context_puts_critical_projects_first(tmp_path):
    make_note(tmp_path, "AAA-1", "---\ntitle: Calm\n---\n", days_ago=9)
    make_note(tmp_path, "ZZZ-1", "---\ntitle: Fire\npriority: critical\n---\n")
    all_text = "\n".join(texts(claude_chat.all_projects_context(tmp_path, NOW)[0]))
    assert all_text.index("Fire") < all_text.index("Calm")


def test_all_context_skips_notes_over_the_size_cap(tmp_path):
    make_note(tmp_path, "DEMO-1", "---\ntitle: Small\npriority: critical\n---\n")
    make_note(tmp_path, "DEMO-2", "---\ntitle: Big\n---\n" + "x" * 200)
    blocks, skipped = claude_chat.all_projects_context(tmp_path, NOW, cap=100)
    assert "Big" not in "\n".join(texts(blocks))
    assert skipped == ["DEMO-2/note.md (over the 100-character limit: raise text_limit= in settings.ini)"]


def test_all_context_with_no_open_projects_says_so(tmp_path):
    blocks, _ = claude_chat.all_projects_context(tmp_path, NOW)
    assert "no open projects" in texts(blocks)[-1].lower()


def test_all_context_marks_its_last_block_for_caching(tmp_path):
    make_note(tmp_path, "DEMO-1", "---\ntitle: Report\n---\n")
    blocks, _ = claude_chat.all_projects_context(tmp_path, NOW)
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}


# ---------- ask: one question, one answer ----------

class FakeClaude:
    """Stands in for anthropic.Anthropic(). Remembers the request, returns a canned answer or raises."""

    def __init__(self, text="Next: ask the vendor.", stop_reason="end_turn", error=None, proposal=None):
        self.request = None
        self.messages = self
        content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
        if proposal is not None:         # Claude calls the propose_changes tool
            content.append(SimpleNamespace(type="tool_use", id="t1", name="propose_changes", input=proposal))
            stop_reason = "tool_use"
        self.reply = SimpleNamespace(content=content, stop_reason=stop_reason)
        self.error = error

    def create(self, **request):
        self.request = request
        if self.error:
            raise self.error
        return self.reply


CONTEXT = [{"type": "text", "text": "the project"}]


def test_ask_sends_context_and_question_and_returns_the_text():
    fake = FakeClaude()
    answer, proposal = claude_chat.ask(fake, "claude-sonnet-5-5", CONTEXT, [], "What's next?")
    assert answer == "Next: ask the vendor."
    assert proposal is None
    assert fake.request["model"] == "claude-sonnet-5-5"
    assert fake.request["messages"] == [
        {"role": "user", "content": CONTEXT + [{"type": "text", "text": "What's next?"}]}]
    assert "notes" in fake.request["system"]


def test_ask_sends_the_earlier_chat_after_the_context():
    fake = FakeClaude()
    history = [{"role": "user", "text": "Hi"}, {"role": "assistant", "text": "Hello"}]
    claude_chat.ask(fake, "m", CONTEXT, history, "And now?")
    assert fake.request["messages"] == [
        {"role": "user", "content": CONTEXT + [{"type": "text", "text": "Hi"}]},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "And now?"}]


def test_ask_about_all_projects_uses_its_own_instructions():
    fake = FakeClaude()
    claude_chat.ask(fake, "m", CONTEXT, [], "q", system=claude_chat.ALL_SYSTEM)
    assert fake.request["system"] == claude_chat.ALL_SYSTEM
    assert "tools" not in fake.request


def test_ask_explains_a_refusal():
    answer, _ = claude_chat.ask(FakeClaude(text="", stop_reason="refusal"), "m", CONTEXT, [], "q")
    assert "declined" in answer


def test_ask_says_when_the_answer_was_cut_short():
    answer, _ = claude_chat.ask(FakeClaude(text="Part one", stop_reason="max_tokens"), "m", CONTEXT, [], "q")
    assert answer.startswith("Part one") and "cut short" in answer


# ---------- proposals: Claude suggests, the person approves ----------

PROPOSAL = {"fields": [{"field": "next", "value": "send the  report\n to Mike"}, {"field": "blocked_by", "value": ""}],
            "history_line": "Vendor  replied:\nonly Northeast", "session_note": "  ## 2026-10-16\nRead the reply.\n  "}


def test_ask_offers_the_propose_tool_only_when_allowed():
    fake = FakeClaude()
    claude_chat.ask(fake, "m", CONTEXT, [], "q")
    assert "tools" not in fake.request
    claude_chat.ask(fake, "m", CONTEXT, [], "q", can_propose=True)
    tool = fake.request["tools"][0]
    assert tool["name"] == "propose_changes"
    allowed = tool["input_schema"]["properties"]["fields"]["items"]["properties"]["field"]["enum"]
    assert "priority" not in allowed and "next" in allowed       # priority is only ever set by the person
    assert "working_on" in allowed
    assert "propose_changes" in fake.request["system"]


def test_ask_returns_claudes_proposal_cleaned_up():
    answer, proposal = claude_chat.ask(FakeClaude(text="Here is my update.", proposal=PROPOSAL),
                                       "m", CONTEXT, [], "q", can_propose=True)
    assert answer == "Here is my update."
    assert proposal == {"fields": [{"field": "next", "value": "send the report to Mike"},
                                   {"field": "blocked_by", "value": ""}],
                        "history_line": "Vendor replied: only Northeast",
                        "session_note": "## 2026-10-16\nRead the reply."}


def test_ask_with_a_proposal_but_no_words_still_says_something():
    answer, proposal = claude_chat.ask(FakeClaude(text="", proposal=PROPOSAL), "m", CONTEXT, [], "q", can_propose=True)
    assert answer and proposal


def test_ask_drops_a_proposal_the_app_cannot_use_and_says_why():
    bad = {**PROPOSAL, "fields": [{"field": "priority", "value": "critical"}]}
    answer, proposal = claude_chat.ask(FakeClaude(text="Done.", proposal=bad), "m", CONTEXT, [], "q", can_propose=True)
    assert proposal is None
    assert answer.startswith("Done.") and "priority" in answer


@pytest.mark.parametrize("bad, words", [
    ("junk", "mixed up"),
    ({**PROPOSAL, "fields": [{"field": "priority", "value": "high"}]}, "priority"),
    ({**PROPOSAL, "fields": [{"field": "jira", "value": "X-1"}]}, "jira"),
    ({**PROPOSAL, "fields": [{"field": "status", "value": "done"}]}, "status"),
    ({**PROPOSAL, "fields": [{"field": "title", "value": "  "}]}, "name"),
    ({**PROPOSAL, "fields": ["next"]}, "mixed up"),
    ({**PROPOSAL, "history_line": 5}, "mixed up"),
])
def test_clean_proposal_refuses_what_it_must_not_change(bad, words):
    with pytest.raises(ValueError, match=words):
        claude_chat.clean_proposal(bad)


def test_clean_proposal_with_nothing_in_it_is_none():
    assert claude_chat.clean_proposal({"fields": [], "history_line": " ", "session_note": ""}) is None


def test_clean_proposal_keeps_the_last_value_of_a_repeated_field():
    proposal = claude_chat.clean_proposal({**PROPOSAL, "fields": [{"field": "next", "value": "a"},
                                                                  {"field": "next", "value": "b"}]})
    assert proposal["fields"] == [{"field": "next", "value": "b"}]


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls, code):
    return cls("boom", response=httpx2.Response(code, request=REQUEST), body=None)


@pytest.mark.parametrize("error, words", [
    (status_error(anthropic.AuthenticationError, 401), "login"),
    (status_error(anthropic.NotFoundError, 404), "model="),
    (status_error(anthropic.RateLimitError, 429), "busy"),
    (anthropic.APIConnectionError(request=REQUEST), "reach"),
    (status_error(anthropic.InternalServerError, 500), "500"),
])
def test_ask_turns_api_errors_into_plain_english(error, words):
    with pytest.raises(claude_chat.ClaudeError, match=words):
        claude_chat.ask(FakeClaude(error=error), "m", CONTEXT, [], "q")


def test_plain_error_names_the_model_when_it_is_not_found():
    assert '"claude-x"' in claude_chat.plain_error(status_error(anthropic.NotFoundError, 404), "claude-x")


def test_plain_error_when_the_login_may_not_use_the_model():
    assert "not allowed" in claude_chat.plain_error(status_error(anthropic.PermissionDeniedError, 403), "m")


def test_plain_error_for_a_server_problem_says_what_to_do():
    words = claude_chat.plain_error(status_error(anthropic.InternalServerError, 529), "m")
    assert "529" in words and "Wait a minute" in words


def test_make_client_without_any_login_says_how_to_fix_it(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(claude_chat.ClaudeError, match="ANTHROPIC_API_KEY"):
        claude_chat.make_client()
