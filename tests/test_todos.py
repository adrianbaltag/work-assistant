"""The To do page's list: todos.md in the projects folder (todos.py, no Flask)."""
import threading
import time

import pytest

import todos

FILE = """# To do (edited by the Work Assistant To do page)

- [ ] (high) call the vendor back
- [ ] tidy the test folder
- [x] send the weekly report
- [x] (high) book the lab slot
- [ ] water the plants
"""


def todo(text, high=False, done=False):
    return {"text": text, "high": high, "done": done}


def write(folder, text=FILE):
    (folder / todos.TODO_FILE).write_text(text, encoding="utf-8")


def file_text(folder):
    return (folder / todos.TODO_FILE).read_text(encoding="utf-8")


# ---------- parse / format_todos ----------

def test_parse_reads_every_kind_of_line_in_file_order():
    assert todos.parse(FILE) == [
        todo("call the vendor back", high=True),
        todo("tidy the test folder"),
        todo("send the weekly report", done=True),
        todo("book the lab slot", high=True, done=True),
        todo("water the plants"),
    ]


def test_parse_accepts_a_capital_x():
    assert todos.parse("- [X] done one\n- [X] (high) done high\n") == [
        todo("done one", done=True), todo("done high", high=True, done=True)]


def test_parse_skips_header_blank_and_stray_lines_and_trims_text():
    text = "# To do\n\nsome stray note\n- [?] odd box\n[ ] no bullet\n- [ ]   spaced out   \n\n"
    assert todos.parse(text) == [todo("spaced out")]


@pytest.mark.parametrize("line, expected", [
    ("* [ ] star bullet", todo("star bullet")),
    ("+ [ ] plus bullet", todo("plus bullet")),
    ("-[ ] no space after the dash", todo("no space after the dash")),
    ("-  [ ] two spaces", todo("two spaces")),
    ("- [ ]no space after the box", todo("no space after the box")),
    ("- [] empty box", todo("empty box")),
    ("* [x](high) all squashed", todo("all squashed", high=True, done=True)),
])
def test_parse_accepts_near_miss_lines_typed_by_hand(line, expected):
    assert todos.parse(line + "\n") == [expected]


def test_parse_reads_a_windows_crlf_file():
    assert todos.parse(FILE.replace("\n", "\r\n")) == todos.parse(FILE)


@pytest.mark.parametrize("text", ["café ☕ with Zoë", "- [ ] looks like a todo inside", "a [x] b"])
def test_odd_text_survives_format_then_parse(text):
    assert todos.parse(todos.format_todos([todo(text)])) == [todo(text)]


def test_parse_skips_a_todo_with_no_text():
    assert todos.parse("- [ ] \n- [ ] (high)\n- [x]\n") == []


def test_format_todos_writes_header_blank_line_and_one_line_each():
    text = todos.format_todos([todo("a", high=True), todo("b"), todo("c", done=True), todo("d", high=True, done=True)])
    assert text == (todos.HEADER + "\n\n"
                    "- [ ] (high) a\n- [ ] b\n- [x] c\n- [x] (high) d\n")


def test_format_todos_with_no_todos_is_just_the_header():
    assert todos.format_todos([]) == todos.HEADER + "\n\n"


def test_format_then_parse_gives_the_same_list():
    items = todos.parse(FILE)
    assert todos.parse(todos.format_todos(items)) == items
    assert todos.format_todos(items) == FILE


# ---------- clean_text ----------

def test_clean_text_trims():
    assert todos.clean_text("  ring the NOC  ") == "ring the NOC"


@pytest.mark.parametrize("text", ["", "   ", "\t"])
def test_clean_text_refuses_empty(text):
    with pytest.raises(ValueError, match="Type something"):
        todos.clean_text(text)


# Every character Python's splitlines() breaks on (parse reads the file with it): Enter and the hidden ones
# Word/Excel can paste. Each becomes one space, so nothing after it is lost.
@pytest.mark.parametrize("brk", ["\n", "\r", "\r\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85",
                                 "\u2028", "\u2029", "\n\n  \n"])
def test_clean_text_turns_line_breaks_into_one_space(brk):
    assert todos.clean_text(f"two{brk}lines") == "two lines"
    assert todos.parse(todos.format_todos([todo(todos.clean_text(f"two{brk}lines"))])) == [todo("two lines")]


def test_clean_text_a_broken_character_becomes_a_question_mark():
    # A lone half of an emoji (JSON can carry one from a bad paste) can't be saved as UTF-8.
    assert todos.clean_text("bad \ud800 paste") == "bad ? paste"


def test_clean_text_errors_are_bad_text():
    with pytest.raises(todos.BadText):
        todos.clean_text("   ")


def test_clean_text_only_line_breaks_is_empty():
    with pytest.raises(ValueError, match="Type something"):
        todos.clean_text("\n\x0b\u2028")


def test_clean_text_keeps_the_longest_allowed_text():
    text = "x" * todos.MAX_LENGTH
    assert todos.clean_text(text) == text


def test_clean_text_refuses_text_that_is_too_long():
    with pytest.raises(ValueError) as err:
        todos.clean_text("x" * (todos.MAX_LENGTH + 1))
    assert str(err.value) == todos.TOO_LONG


def test_clean_text_trailing_line_break_is_just_trimmed():
    assert todos.clean_text("one line\n") == "one line"


@pytest.mark.parametrize("text", ["(high) fix it", "  (HIGH) fix it", "(High)"])
def test_clean_text_refuses_a_high_prefix(text):
    with pytest.raises(ValueError) as err:
        todos.clean_text(text)
    assert str(err.value) == todos.HIGH_PREFIX


def test_clean_text_allows_high_later_in_the_text():
    assert todos.clean_text("fix it (high) now") == "fix it (high) now"


# ---------- read_todos ----------

def test_read_todos_no_file_is_an_empty_list(tmp_path):
    assert todos.read_todos(tmp_path) == []


def test_read_todos_reads_the_file(tmp_path):
    write(tmp_path)
    assert todos.read_todos(tmp_path) == todos.parse(FILE)


def test_read_todos_a_bom_does_not_break_the_first_line(tmp_path):
    (tmp_path / todos.TODO_FILE).write_text("- [ ] first one\n- [ ] second\n", encoding="utf-8-sig")
    assert todos.read_todos(tmp_path) == [todo("first one"), todo("second")]


def test_read_todos_not_utf8_says_how_to_fix_it(tmp_path):
    (tmp_path / todos.TODO_FILE).write_bytes("- [ ] caf\xe9\n".encode("cp1252"))   # what old Notepad saves
    with pytest.raises(todos.Unreadable) as err:
        todos.read_todos(tmp_path)
    assert str(err.value) == todos.NOT_UTF8


def test_read_todos_no_projects_folder_says_how_to_fix_it(tmp_path):
    with pytest.raises(todos.Unreadable) as err:
        todos.read_todos(tmp_path / "gone")
    assert str(err.value) == todos.NO_FOLDER.format(tmp_path / "gone")


def test_a_failed_save_leaves_the_old_file(tmp_path, monkeypatch):
    write(tmp_path)
    monkeypatch.setattr(todos, "format_todos", lambda items: "can't be saved \ud800")
    with pytest.raises(UnicodeEncodeError):
        todos.add(tmp_path, "new one")
    assert file_text(tmp_path) == FILE         # not emptied


def test_read_todos_a_folder_called_todos_md_says_how_to_fix_it(tmp_path):
    (tmp_path / todos.TODO_FILE).mkdir()
    with pytest.raises(todos.Unreadable) as err:
        todos.read_todos(tmp_path)
    assert str(err.value) == todos.NOT_A_FILE


# ---------- listing ----------

def test_listing_display_order_rows_and_counts():
    result = todos.listing(todos.parse(FILE))
    assert [(t["text"], t["row"]) for t in result["todos"]] == [
        ("call the vendor back", 0),
        ("tidy the test folder", 1),
        ("water the plants", 4),
        ("send the weekly report", 2),
        ("book the lab slot", 3),
    ]
    assert result["todos"][0] == {"text": "call the vendor back", "high": True, "done": False, "row": 0}
    assert (result["open"], result["open_high"], result["done"]) == (3, 1, 2)


def test_listing_keeps_file_order_inside_each_group():
    items = [todo("n1"), todo("h1", high=True), todo("d1", done=True), todo("n2"), todo("h2", high=True)]
    assert [t["text"] for t in todos.listing(items)["todos"]] == ["h1", "h2", "n1", "n2", "d1"]


def test_listing_empty():
    assert todos.listing([]) == {"todos": [], "open": 0, "open_high": 0, "done": 0}


def test_listing_does_not_change_the_todos_passed_in():
    items = [todo("a")]
    todos.listing(items)
    assert items == [todo("a")]


# ---------- add ----------

def test_add_creates_the_file_on_the_first_add(tmp_path):
    todos.add(tmp_path, "  ring the NOC ")
    assert file_text(tmp_path) == todos.HEADER + "\n\n- [ ] ring the NOC\n"


def test_add_appends_a_normal_open_todo_at_the_end(tmp_path):
    write(tmp_path)
    todos.add(tmp_path, "new one")
    assert todos.read_todos(tmp_path)[-1] == todo("new one")
    assert file_text(tmp_path) == FILE + "- [ ] new one\n"


def test_add_refuses_bad_text_and_writes_no_file(tmp_path):
    with pytest.raises(ValueError):
        todos.add(tmp_path, "   ")
    assert not (tmp_path / todos.TODO_FILE).exists()


def test_add_drops_stray_lines_and_writes_the_header(tmp_path):
    write(tmp_path, "my own title\n- [ ] keep me\nrandom words\n")
    todos.add(tmp_path, "second")
    assert file_text(tmp_path) == todos.HEADER + "\n\n- [ ] keep me\n- [ ] second\n"


# ---------- set_done / set_high / set_text / delete ----------

def test_set_done_ticks_and_unticks_the_right_row(tmp_path):
    write(tmp_path)
    todos.set_done(tmp_path, 1, "tidy the test folder", True)
    assert todos.read_todos(tmp_path)[1] == todo("tidy the test folder", done=True)
    todos.set_done(tmp_path, 1, "tidy the test folder", False)
    assert todos.read_todos(tmp_path) == todos.parse(FILE)


def test_set_done_a_high_todo_stays_high(tmp_path):
    write(tmp_path)
    todos.set_done(tmp_path, 0, "call the vendor back", True)
    assert todos.read_todos(tmp_path)[0] == todo("call the vendor back", high=True, done=True)
    todos.set_done(tmp_path, 3, "book the lab slot", False)
    assert todos.read_todos(tmp_path)[3] == todo("book the lab slot", high=True)


def test_set_high_on_and_off(tmp_path):
    write(tmp_path)
    todos.set_high(tmp_path, 4, "water the plants", True)
    assert todos.read_todos(tmp_path)[4] == todo("water the plants", high=True)
    todos.set_high(tmp_path, 0, "call the vendor back", False)
    assert todos.read_todos(tmp_path)[0] == todo("call the vendor back")


def test_set_text_changes_the_words_and_keeps_the_flags(tmp_path):
    write(tmp_path)
    todos.set_text(tmp_path, 3, "book the lab slot", "  book the big lab ")
    assert todos.read_todos(tmp_path)[3] == todo("book the big lab", high=True, done=True)


@pytest.mark.parametrize("bad", ["", "x" * (todos.MAX_LENGTH + 1), "(high) sneaky"])
def test_set_text_refuses_bad_text_and_leaves_the_file(tmp_path, bad):
    write(tmp_path)
    with pytest.raises(ValueError):
        todos.set_text(tmp_path, 1, "tidy the test folder", bad)
    assert file_text(tmp_path) == FILE


def test_delete_removes_the_right_row(tmp_path):
    write(tmp_path)
    todos.delete(tmp_path, 2, "send the weekly report")
    assert [t["text"] for t in todos.read_todos(tmp_path)] == [
        "call the vendor back", "tidy the test folder", "book the lab slot", "water the plants"]


CHANGES = [
    lambda folder, row, text: todos.set_done(folder, row, text, True),
    lambda folder, row, text: todos.set_high(folder, row, text, True),
    lambda folder, row, text: todos.set_text(folder, row, text, "new words"),
    lambda folder, row, text: todos.delete(folder, row, text),
]


@pytest.mark.parametrize("change", CHANGES)
@pytest.mark.parametrize("row, text", [
    (5, "water the plants"),            # past the end
    (-1, "water the plants"),           # negative (Python would read it as the last one)
    ("1", "tidy the test folder"),      # not an int
    (1.0, "tidy the test folder"),
    (True, "tidy the test folder"),     # bool is an int in Python
    (None, "tidy the test folder"),
    (1, "call the vendor back"),        # text doesn't match the row
])
def test_a_changed_list_saves_nothing(tmp_path, change, row, text):
    write(tmp_path)
    with pytest.raises(todos.ListChanged):
        change(tmp_path, row, text)
    assert file_text(tmp_path) == FILE


@pytest.mark.parametrize("change", CHANGES)
def test_a_change_with_no_file_is_a_changed_list(tmp_path, change):
    with pytest.raises(todos.ListChanged):
        change(tmp_path, 0, "anything")
    assert not (tmp_path / todos.TODO_FILE).exists()


# ---------- clear_done ----------

SHOWN_DONE = ["send the weekly report", "book the lab slot"]      # the done todos in FILE, file order


def test_clear_done_removes_every_done_todo(tmp_path):
    write(tmp_path)
    kept = [todo("call the vendor back", high=True), todo("tidy the test folder"), todo("water the plants")]
    assert todos.clear_done(tmp_path, SHOWN_DONE) == kept
    assert todos.read_todos(tmp_path) == kept


def test_clear_done_none_done_writes_nothing(tmp_path):
    write(tmp_path, "- [ ] only open\n")
    assert todos.clear_done(tmp_path, []) == [todo("only open")]
    assert file_text(tmp_path) == "- [ ] only open\n"


def test_clear_done_with_no_file_writes_nothing(tmp_path):
    assert todos.clear_done(tmp_path, []) == []
    assert not (tmp_path / todos.TODO_FILE).exists()


# The page sends the done todos it showed in "Delete N done todos for good?". Different from the file
# (another tab ticked or unticked one meanwhile) = nothing deleted that you didn't see.
@pytest.mark.parametrize("shown", [
    ["send the weekly report"],                                     # one more was ticked elsewhere
    SHOWN_DONE + ["tidy the test folder"],                          # one was unticked elsewhere
    list(reversed(SHOWN_DONE)),
    [],
])
def test_clear_done_refuses_when_the_done_list_changed(tmp_path, shown):
    write(tmp_path)
    with pytest.raises(todos.ListChanged):
        todos.clear_done(tmp_path, shown)
    assert file_text(tmp_path) == FILE


# ---------- each change returns the new list (so the app answers without reading the file again) ----------

def test_each_change_returns_the_list_it_saved(tmp_path):
    write(tmp_path)
    for change in [lambda: todos.add(tmp_path, "new one"),
                   lambda: todos.set_done(tmp_path, 1, "tidy the test folder", True),
                   lambda: todos.set_high(tmp_path, 1, "tidy the test folder", True),
                   lambda: todos.set_text(tmp_path, 1, "tidy the test folder", "tidy it"),
                   lambda: todos.delete(tmp_path, 0, "call the vendor back")]:
        assert change() == todos.read_todos(tmp_path)


# ---------- two changes at the same moment (Flask answers each click on its own thread) ----------

def test_changes_at_the_same_moment_do_not_lose_each_other(tmp_path, monkeypatch):
    write(tmp_path, "")
    real_read = todos.read_todos

    def slow_read(folder):          # widen the gap between reading the file and writing it back
        found = real_read(folder)
        time.sleep(0.05)
        return found
    monkeypatch.setattr(todos, "read_todos", slow_read)
    threads = [threading.Thread(target=todos.add, args=(tmp_path, f"todo {n}")) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(t["text"] for t in real_read(tmp_path)) == [f"todo {n}" for n in range(5)]
