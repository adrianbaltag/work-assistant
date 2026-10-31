"""One id = one element. The page (index.html) and the HTML the scripts build must never share an id:
$("f-status") returns the FIRST element with that id, so a clash makes one script read the other's box.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
ID = re.compile(r'(?<![\w-])id="([\w-]+)"')     # id="…", not data-id="…"


def page_ids():
    return ID.findall((ROOT / "templates" / "index.html").read_text(encoding="utf-8"))


def card_field_ids():
    """card.js builds one box per field: id="f-${key}" for each key in FIELDS."""
    card = (ROOT / "static" / "card.js").read_text(encoding="utf-8")
    fields = re.search(r"const FIELDS = \[(.*?)\];", card).group(1)
    return {"f-" + key for key in re.findall(r'"(\w+)"', fields)}


def script_ids():
    found = set(card_field_ids())
    for script in (ROOT / "static").glob("*.js"):
        found |= set(ID.findall(script.read_text(encoding="utf-8")))
    return found


def test_the_page_has_no_id_twice():
    ids = page_ids()
    assert len(ids) == len(set(ids)), sorted(i for i in set(ids) if ids.count(i) > 1)


def test_scripts_never_build_an_id_the_page_already_has():
    assert set(page_ids()) & script_ids() == set()


def test_the_card_fields_are_found():
    assert {"f-status", "f-priority", "f-title"} <= card_field_ids()
