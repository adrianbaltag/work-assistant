"""Small text on the page must be easy to read: WCAG AA, at least 4.5:1 against what is behind it.

The test reads static/app.css itself, so it checks the colours the page really uses. Each case names
the text's rule and the backgrounds under it, bottom first. A see-through background (8-digit hex)
is mixed with the one under it, the way the browser does.
"""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parent.parent / "static" / "app.css").read_text(encoding="utf-8")
AA = 4.5


def parse_rules(css):
    """Map each selector to its declarations. Later rules win, like in the browser."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    rules = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        decls = {}
        for part in body.split(";"):
            if ":" in part:
                prop, val = part.split(":", 1)
                decls[prop.strip()] = val.strip()
        for sel in selectors.split(","):
            rules.setdefault(sel.strip(), {}).update(decls)
    return rules


RULES = parse_rules(CSS)
ROOT = RULES[":root"]


def value(selector, prop):
    """The colour (hex) a rule sets for prop. var(--x) is looked up in the rule first, then in :root."""
    own = RULES[selector]
    text = own[prop]
    for _ in range(5):                                  # a token may point to another token
        text = re.sub(r"var\((--[\w-]+)\)", lambda m: own.get(m.group(1), ROOT[m.group(1)]), text)
    found = re.search(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\b", text)
    assert found, f"{selector} {prop} has no hex colour: {text}"
    return found.group(0)


def mix(top, under):
    """A see-through colour (#RRGGBBAA) painted over a solid one."""
    if len(top) == 7:
        return top
    alpha = int(top[7:9], 16) / 255
    return "#" + "".join(
        f"{round(int(top[i:i + 2], 16) * alpha + int(under[i:i + 2], 16) * (1 - alpha)):02X}" for i in (1, 3, 5))


def luminance(hex_colour):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    light, dark = sorted([luminance(a), luminance(b)], reverse=True)
    return (light + 0.05) / (dark + 0.05)


def behind(*layers):
    """The colour you see after painting each background over the one before it."""
    colour = value(*layers[0])
    for layer in layers[1:]:
        colour = mix(value(*layer), colour)
    return colour


def winner(*candidates):
    """The first (selector, prop) that the CSS really has: a specific hover rule beats the general one."""
    for selector, prop in candidates:
        if prop in RULES.get(selector, {}):
            return selector, prop
    raise AssertionError(f"none of these rules exist: {candidates}")


ROW, HOVERED_ROW = (".plist", "background"), (".prow:hover", "background")
NOTE_BOX, CARD = (".box", "background"), (".modal", "background")
SLACK_LIST, SLACK_HOVER = (".slack-dd", "background"), (".dd-item:hover", "background")
PAGE, BUTTON_HOVER = ("body", "background"), (".btn:not([disabled]):hover", "background")

CASES = [
    ("error in the Note box", (".err", "color"), [NOTE_BOX]),
    ("critical tag on a row", (".pr-critical", "--c"), [ROW, (".pr-critical", "--soft")]),
    ("critical tag on a hovered row", (".pr-critical", "--c"), [HOVERED_ROW, (".pr-critical", "--soft")]),
    ("Delete button", (".btn.danger", "color"), [CARD, (".btn.danger", "background")]),
    ("Delete button, hovered", (".btn.danger", "color"),
     [CARD, winner((".btn.danger:not([disabled]):hover", "background"), BUTTON_HOVER)]),
    ("Ask Claude button, hovered", (".btn.claude", "color"),
     [PAGE, winner((".btn.claude:not([disabled]):hover", "background"), BUTTON_HOVER)]),
    ("Clear done button, hovered", (".btn.clear", "color"),
     [(".tcard.done", "background"), (".btn.clear:not([disabled]):hover", "background")]),
    ("title of a red warning",(".alert.bad b", "color"), [CARD, (".alert.bad", "background")]),
    ("History name tag", (".log .who", "color"), [NOTE_BOX, (".log .who", "background")]),
    ("Claude name tag in History", (".log .who.c", "color"), [NOTE_BOX, (".log .who.c", "background")]),
    ("idea tag on a hovered row", (".st-idea", "--c"), [HOVERED_ROW, (".st-idea", "--soft")]),
    ("idea tag in a card box", (".st-idea", "--c"), [NOTE_BOX, (".st-idea", "--soft")]),
    ("blocker tag in the card", (".by", "color"), [NOTE_BOX, (".by", "background")]),
    ("blocker tag on a hovered row", (".by", "color"), [HOVERED_ROW, (".by", "background")]),
    ("Slack initials", (".av", "color"), [SLACK_LIST, (".av", "background")]),
    ("Slack initials on a hovered row", (".av", "color"), [SLACK_LIST, SLACK_HOVER, (".av", "background")]),
    ("Slack channel name, hovered", (".dd-where", "color"), [SLACK_LIST, SLACK_HOVER]),
    ("Slack time, hovered", (".dd-ago", "color"), [SLACK_LIST, SLACK_HOVER]),
    ("Slack tag, hovered", (".dd-tag", "color"), [SLACK_LIST, SLACK_HOVER]),
    ("gone-quiet time on a row", (".ago.q", "color"), [ROW]),
    ("gone-quiet time on a hovered row", (".ago.q", "color"), [HOVERED_ROW]),
    ("current page in the sidebar", ('.nav[aria-current="page"]', "color"), [('.nav[aria-current="page"]', "background")]),
    ("In progress label on a row", (".pend .wait", "color"), [ROW]),
    ("In progress label on a hovered row", (".pend .wait", "color"), [ROW, (".prow-wrap:hover", "background")]),
    ("Complete button on a row", (".pend .go", "color"), [(".pend .go", "background")]),
    ("Complete button on a row, hovered", (".pend .go", "color"), [("button.pend:hover .go", "background")]),
    ("Move to Completed button", (".btn.complete", "color"), [(".btn.complete", "background")]),
    ("Move to Completed button, hovered", (".btn.complete", "color"),
     [(".btn.complete:not([disabled]):hover", "background")]),
]


@pytest.mark.parametrize("name, text, layers", CASES, ids=[c[0] for c in CASES])
def test_small_text_is_easy_to_read(name, text, layers):
    ratio = contrast(value(*text), behind(*layers))
    assert ratio >= AA, f"{name}: {ratio:.2f}:1, needs {AA}:1"


@pytest.mark.parametrize("box, under", [
    (".later", (".side", "background")),       # "Coming later" in the sidebar
    (".tempty", (".tempty", "background")),    # the empty To do box
])
def test_a_dashed_box_edge_is_lighter_than_what_is_behind_it(box, under):
    # The lines are darker than every background ("carved in"), but a dashed edge that is darker
    # than its own background just disappears: it must be the lighter edge colour.
    assert luminance(value(box, "border")) > luminance(value(*under))


def test_the_current_sidebar_page_is_filled_with_the_accent():
    assert value('.nav[aria-current="page"]', "background") == ROOT["--accent"]


ICONS = {".tflag.on", ".tdel:hover", ".thead .ico"}     # red icons, not words: the full red is fine there


def test_red_words_use_the_lighter_red():
    # Your rule (2026-11-21): words get --critical-text; only dots, counts, badges, icons and filled
    # buttons (red background) keep the full --critical.
    for selector, decls in RULES.items():
        if decls.get("color") == "var(--critical)" and selector not in ICONS:
            assert decls.get("background") == "var(--critical)", f"{selector} uses the full red for words"


def test_slack_initials_keep_slack_purple():
    colour = value(".av", "color")
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    assert b == max(r, g, b) and b - g >= 0x30, f"{colour} is not purple: colour = meaning, purple = Slack"


def test_words_coloured_in_the_page_scripts_use_the_lighter_shades():
    # Some words get their colour inline from the JS (the dashboard summary line), so app.css alone is not enough.
    for js in sorted((Path(__file__).resolve().parent.parent / "static").glob("*.js")):
        found = re.findall(r'style="color:var\(--(critical|quiet)\)"', js.read_text(encoding="utf-8"))
        assert not found, f"{js.name}: words in the full {found} colour, use --{found[0]}-text"


def test_the_slack_tag_uses_the_same_purple_as_the_initials():
    assert RULES[".dd-tag"]["color"] == RULES[".av"]["color"] == "var(--slack-text)"
