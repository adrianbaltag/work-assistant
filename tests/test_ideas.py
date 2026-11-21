"""The Ideas page's list: ideas.md in the projects folder (ideas.py)."""
import pytest

import ideas

FILE = """# Ideas (edited by the Work Assistant Ideas page)

## 2026-11-21 · Rename old scripts
They all start with tmp_.
Pick one style.

## 2026-11-20 · A quick one
"""


@pytest.fixture
def folder(tmp_path):
    (tmp_path / ideas.IDEA_FILE).write_text(FILE, encoding="utf-8")
    return tmp_path


# ---------- reading the file ----------

def test_parse_reads_each_idea_in_file_order():
    assert ideas.parse(FILE) == [
        {"date": "2026-11-21", "name": "Rename old scripts", "details": "They all start with tmp_.\nPick one style."},
        {"date": "2026-11-20", "name": "A quick one", "details": ""},
    ]


def test_parse_reads_a_windows_crlf_file():
    assert ideas.parse(FILE.replace("\n", "\r\n")) == ideas.parse(FILE)


def test_parse_skips_text_before_the_first_idea():
    assert ideas.parse("# Ideas\nstray line\n\n## 2026-11-21 · One\n") == [
        {"date": "2026-11-21", "name": "One", "details": ""}]


def test_parse_accepts_a_heading_typed_by_hand_without_a_date():
    assert ideas.parse("## Just a name\nmore\n") == [{"date": "", "name": "Just a name", "details": "more"}]


def test_parse_keeps_one_blank_line_inside_details_and_trims_the_edges():
    text = "## 2026-11-21 · One\n\n  first  \n\n\n\nsecond\n\n"
    assert ideas.parse(text)[0]["details"] == "first\n\nsecond"


def test_parse_gives_a_heading_with_no_name_a_stand_in_name():
    assert ideas.parse("## 2026-11-21 · \ndetails\n")[0]["name"] == ideas.NO_NAME


def test_parse_drops_an_empty_heading_with_nothing_under_it():
    assert ideas.parse("## \n\n## 2026-11-21 · Kept\n") == [{"date": "2026-11-21", "name": "Kept", "details": ""}]


def test_format_then_parse_gives_the_same_ideas():
    assert ideas.parse(ideas.format_ideas(ideas.parse(FILE))) == ideas.parse(FILE)


def test_format_starts_with_the_header():
    assert ideas.format_ideas([]).startswith(ideas.HEADER)


def test_a_details_line_that_looks_like_a_heading_stays_inside_its_idea():
    saved = ideas.format_ideas([{"date": "2026-11-21", "name": "One", "details": "## not a new idea"}])
    assert ideas.parse(saved) == [{"date": "2026-11-21", "name": "One", "details": "## not a new idea"}]


def test_read_with_no_file_yet_is_an_empty_list(tmp_path):
    assert ideas.read_ideas(tmp_path) == []


def test_read_a_missing_projects_folder_says_what_to_fix(tmp_path):
    with pytest.raises(ideas.Unreadable, match="projects_folder="):
        ideas.read_ideas(tmp_path / "gone")


def test_read_a_folder_named_ideas_md_says_rename_it(tmp_path):
    (tmp_path / ideas.IDEA_FILE).mkdir()
    with pytest.raises(ideas.Unreadable, match="Rename it"):
        ideas.read_ideas(tmp_path)


def test_read_a_file_that_is_not_utf8_says_how_to_fix(tmp_path):
    (tmp_path / ideas.IDEA_FILE).write_bytes("## 2026-11-21 · caf\xe9\n".encode("latin-1"))
    with pytest.raises(ideas.Unreadable, match="UTF-8"):
        ideas.read_ideas(tmp_path)


# ---------- typed text ----------

def test_clean_first_line_is_the_name_the_rest_is_details():
    assert ideas.clean("  Rename old scripts \nThey all start with tmp_.\n") == (
        "Rename old scripts", "They all start with tmp_.")


def test_clean_skips_blank_lines_before_the_name():
    assert ideas.clean("\n\n  Name\n\n\ndetail") == ("Name", "detail")


def test_clean_refuses_empty_text():
    with pytest.raises(ideas.BadText, match="Type an idea"):
        ideas.clean(" \n \n")


def test_clean_refuses_text_over_the_limit():
    with pytest.raises(ideas.BadText, match=str(ideas.MAX_LENGTH)):
        ideas.clean("x" * (ideas.MAX_LENGTH + 1))


def test_clean_allows_text_at_the_limit():
    assert ideas.clean("x" * ideas.MAX_LENGTH)[0] == "x" * ideas.MAX_LENGTH


def test_clean_turns_a_broken_character_into_a_question_mark():
    assert ideas.clean("half \ud83d emoji")[0] == "half ? emoji"


# ---------- changes ----------

def test_add_puts_the_new_idea_first_with_today(folder):
    saved = ideas.add(folder, "New one\nwith details", "2026-11-22")
    assert saved[0] == {"date": "2026-11-22", "name": "New one", "details": "with details"}
    assert ideas.read_ideas(folder) == saved
    assert len(saved) == 3


def test_add_makes_the_file_on_the_first_idea(tmp_path):
    ideas.add(tmp_path, "First", "2026-11-22")
    assert (tmp_path / ideas.IDEA_FILE).read_text(encoding="utf-8").startswith(ideas.HEADER)


def test_add_what_you_typed_reads_back_the_same(tmp_path):
    saved = ideas.add(tmp_path, "Name\n## heading-like line\n\n\nlast", "2026-11-22")
    assert ideas.read_ideas(tmp_path) == saved


def test_delete_removes_that_idea_for_good(folder):
    saved = ideas.delete(folder, 0, "Rename old scripts")
    assert [i["name"] for i in saved] == ["A quick one"]
    assert ideas.read_ideas(folder) == saved


@pytest.mark.parametrize("row, name", [(0, "A quick one"), (5, "Rename old scripts"), (-1, "A quick one"),
                                       (True, "A quick one"), ("0", "Rename old scripts")])
def test_delete_refuses_when_the_row_and_name_no_longer_match(folder, row, name):
    with pytest.raises(ideas.ListChanged):
        ideas.delete(folder, row, name)
    assert ideas.read_ideas(folder) == ideas.parse(FILE)


def test_get_returns_the_idea_when_row_and_name_match(folder):
    assert ideas.get(folder, 1, "A quick one") == {"date": "2026-11-20", "name": "A quick one", "details": ""}


def test_get_refuses_a_stale_row(folder):
    with pytest.raises(ideas.ListChanged):
        ideas.get(folder, 1, "Rename old scripts")


def test_listing_adds_each_row_and_the_count():
    found = ideas.listing(ideas.parse(FILE))
    assert found["count"] == 2
    assert [(i["row"], i["name"]) for i in found["ideas"]] == [(0, "Rename old scripts"), (1, "A quick one")]
