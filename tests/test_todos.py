"""The To do page's list: todos.md in the projects folder (todos.py, no Flask)."""
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
    text = "# To do\n\nsome stray note\n* [ ] wrong bullet\n- [?] odd box\n-  [ ] no\n- [ ]   spaced out   \n\n"
    assert todos.parse(text) == [todo("spaced out")]


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


@pytest.mark.parametrize("text", ["two\nlines", "two\rlines", "two\r\nlines"])
def test_clean_text_refuses_line_breaks(text):
    with pytest.raises(ValueError) as err:
        todos.clean_text(text)
    assert str(err.value) == todos.ONE_LINE


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


@pytest.mark.parametrize("bad", ["", "a\nb", "(high) sneaky"])
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

def test_clear_done_removes_every_done_todo(tmp_path):
    write(tmp_path)
    assert todos.clear_done(tmp_path) == 2
    assert todos.read_todos(tmp_path) == [
        todo("call the vendor back", high=True), todo("tidy the test folder"), todo("water the plants")]


def test_clear_done_none_done_gives_zero(tmp_path):
    write(tmp_path, "- [ ] only open\n")
    assert todos.clear_done(tmp_path) == 0
    assert todos.read_todos(tmp_path) == [todo("only open")]


def test_clear_done_with_no_file_gives_zero_and_writes_nothing(tmp_path):
    assert todos.clear_done(tmp_path) == 0
    assert not (tmp_path / todos.TODO_FILE).exists()
